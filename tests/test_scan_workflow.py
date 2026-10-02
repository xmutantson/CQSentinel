"""Exercise real scanning/session code with synthetic audio and fake peripherals."""
import threading
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np

from cqsentinel.speech.router import TranscriptionRouter
from cqsentinel.contest.behavior import BehaviorAnalyzer, StationType
from cqsentinel.contest.callsign import CallsignExtractor
from offline_modules import engine, station, recording, signals
from test_config_router import FakeBackend


class Radio:
    def __init__(self):
        self.frequency = 14150000
        self.tunes = []
        self.mode = 'USB'

    def set_frequency(self, frequency):
        self.frequency = frequency
        self.tunes.append(frequency)

    def get_frequency(self):
        return self.frequency

    def set_mode(self, mode, bandwidth):
        self.mode = mode

    def get_mode(self):
        return self.mode, 2400

    def get_strength(self):
        return 5


class Audio:
    sample_rate = 16000
    def record(self, duration, cancel_requested=None):
        return np.ones(int(duration * self.sample_rate), dtype=np.float32)

    def interrupt_recording(self):
        pass


class Pipeline:
    def __init__(self):
        self.local_inference_calls = 0

    def process_quick(self, audio):
        return {'has_speech': True}

    def process(self, audio, transcribe=True):
        if transcribe:
            self.local_inference_calls += 1
            raise AssertionError('Selected remote backend must own transcription')
        return NS(clean_audio=audio, has_speech=True, transcripts=[], voice_segments=[],
                  duration=len(audio) / 16000)


class ImmediateBackend(FakeBackend):
    def transcribe_async(self, **kwargs):
        request_id = super().transcribe_async(**kwargs)
        self.results.put(NS(request_id=request_id, text='CQ contest K1ABC five nine',
                            success=True, frequency_hz=kwargs['frequency_hz']))
        return request_id


class ScanTests(unittest.TestCase):
    def make_scanner(self, backend=None, **kwargs):
        self.radio = Radio()
        self.audio = Audio()
        self.pipeline = Pipeline()
        self.backend = backend if backend is not None else ImmediateBackend()
        self.band_map = station.BandMapState('20m')
        return engine.BandScanner(
            radio_controller=self.radio, audio_capture=self.audio,
            audio_pipeline=self.pipeline, auto_tuner=None,
            auto_center_enabled=False, transcriber=TranscriptionRouter(self.backend),
            callsign_extractor=NS(get_unique_callsigns=lambda text: ['K1ABC']),
            behavior_analyzer=NS(analyze=lambda *args: NS(score=90, is_run_station=True)),
            band_map=self.band_map, dwell_with_voice_sec=.01,
            quick_check_duration=.01, **kwargs)

    def test_selected_backend_completes_scan_and_populates_station(self):
        scanner = self.make_scanner()
        scanner._process_frequency(14150000)
        self.assertEqual(len(self.backend.requests), 1)
        self.assertEqual(self.pipeline.local_inference_calls, 0)
        found = self.band_map.stations[0]
        self.assertEqual(found.callsign, 'K1ABC')
        self.assertEqual(found.frequency, 14150000)
        self.assertIn('CQ contest', found.last_transcript)

    def test_real_transcript_analysis_can_pass_default_threshold_without_voice_id(self):
        transcript = ('CQ Field Day W1AW W1AW 2A CT. K1ABC you are 59 zone 5 roger copy '
            'QSL 73 thanks for the report. N0CALL you are 59 zone 5. W2XYZ roger 2A CT. '
            'K3ABC QSL 59. N4XYZ copy sending report. VE3XYZ thanks for the contact. '
            'K5XYZ QSL QRZ CQ contest.')
        scanner = self.make_scanner(min_contestness_score=70)
        scanner.callsign_ext = CallsignExtractor()
        scanner.behavior = BehaviorAnalyzer(scanner.callsign_ext)
        original_get = self.backend.get_result
        def get_result(timeout=0):
            result = original_get(timeout)
            if result is not None:
                result.text = transcript
            return result
        self.backend.get_result = get_result
        original_process = self.pipeline.process
        def process(*args, **kwargs):
            result = original_process(*args, **kwargs)
            result.duration = 60  # A representative one-minute transcript.
            return result
        self.pipeline.process = process
        scanner._process_frequency(14150000)
        self.assertEqual(len(self.band_map.stations), 1)
        self.assertGreaterEqual(self.band_map.stations[0].contestness_score, 70)
        self.assertEqual(self.band_map.stations[0].activity_type, station.ActivityType.UNCLEAR)
        ragchew = scanner.behavior.analyze('The weather is pleasant and my garden is growing.', 60, [])
        self.assertLess(ragchew.score, 40)
        self.assertEqual(ragchew.station_type, StationType.RAGCHEW)
        self.assertEqual(scanner.behavior.analyze('', 60, []).score, 0)

    def test_stop_during_centering_prevents_subsequent_tuning(self):
        scanner = self.make_scanner()
        scanner.auto_center_enabled = True
        def auto_center(radio, capture, frequency, **kwargs):
            scanner.stop_scan()
            radio.set_frequency(frequency + 100)
            raise AssertionError('Cancelled tuner must not continue')
        scanner.tuner = NS(set_sideband=Mock(), auto_center=auto_center)
        scanner._process_frequency(14150000)
        scanner.tuner.set_sideband.assert_called_once_with('USB')
        self.assertEqual(self.radio.tunes, [14150000])
        self.assertEqual(self.backend.requests, [])

    def test_s_meter_failure_falls_back_to_voice_detection(self):
        scanner = self.make_scanner()
        self.radio.get_strength = Mock(side_effect=RuntimeError('unsupported'))
        scanner._process_frequency(14150000)
        self.assertEqual(len(self.band_map.stations), 1)

    def test_noise_skip_works_before_any_station_has_been_found(self):
        scanner = self.make_scanner()
        scanner.step_delay = 0
        for _ in range(3):
            self.band_map.mark_noise_occurrence(14150000)
        scanner._process_frequency(14150000)
        self.assertEqual(self.radio.tunes, [])
        self.assertEqual(self.backend.requests, [])

    def test_s_meter_failure_with_silence_skips_transcription(self):
        scanner = self.make_scanner()
        scanner.step_delay = 0
        self.radio.get_strength = Mock(side_effect=RuntimeError('unsupported'))
        self.pipeline.process_quick = lambda audio: {'has_speech': False}
        scanner._process_frequency(14150000)
        self.assertEqual(self.backend.requests, [])

    def test_transcription_deadline_expires_without_station(self):
        scanner = self.make_scanner(FakeBackend(), transcription_timeout_sec=0)
        with self.assertLogs(engine.logger, level='ERROR'):
            scanner._process_frequency(14150000)
        self.assertEqual(self.band_map.stations, [])
        self.assertEqual(scanner.transcriber._pending, set())

    def test_stop_during_processing_keeps_worker_owned_until_exit(self):
        scanner = self.make_scanner()
        entered, release = threading.Event(), threading.Event()
        original_process = self.pipeline.process
        def blocked_process(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test release was not signalled')
            return original_process(*args, **kwargs)
        self.pipeline.process = blocked_process
        scanner.start_scan(14150000, 14150000)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(2))
        worker = scanner._scan_thread
        scanner.stop_scan()
        self.assertTrue(scanner.is_scanning())
        self.assertFalse(scanner.wait_stopped(.01))
        scanner.start_scan(14200000, 14200000)
        self.assertIs(scanner._scan_thread, worker)
        release.set()
        self.assertTrue(scanner.wait_stopped(2))
        self.assertEqual(self.backend.requests, [])
        self.assertEqual(self.band_map.stations, [])
        self.assertEqual(self.radio.tunes, [14150000])

    def test_same_scanner_can_restart_after_confirmed_completion(self):
        scanner = self.make_scanner()
        for freq in (14150000, 14200000):
            scanner.start_scan(freq, freq)
            self.assertTrue(scanner.wait_stopped(2))
            self.assertEqual(scanner.progress.total_frequencies, 1)
            self.assertEqual(scanner.progress.progress_percent, 100)
        self.assertEqual(len(self.backend.requests), 2)

    def test_stop_while_waiting_for_transcription_ignores_late_result(self):
        scanner = self.make_scanner(FakeBackend())
        submitted = threading.Event()
        original = self.backend.transcribe_async
        def submit(**kwargs):
            result = original(**kwargs)
            submitted.set()
            return result
        self.backend.transcribe_async = submit
        scanner.start_scan(14150000, 14150000)
        self.assertTrue(submitted.wait(2))
        scanner.stop_scan()
        self.assertTrue(scanner.wait_stopped(2))
        self.backend.results.put(NS(request_id=1, text='late', success=True))
        self.assertIsNone(scanner.transcriber.get_result_for(1))
        self.assertEqual(self.band_map.stations, [])


class SessionTests(unittest.TestCase):
    def make_session(self):
        self.backend = FakeBackend()
        self.router = TranscriptionRouter(self.backend)
        return recording.RecordingSession(
            carrier_detector=NS(last_signal_info=None, reset=lambda: None),
            transcript_analyzer=NS(), transcriber=self.router, auto_center_enabled=False,
            recording_duration=.01, transcription_timeout_sec=0)

    def test_recorded_frequency_is_immutable_when_request_is_submitted(self):
        session = self.make_session()
        session.current_frequency_hz = 14150000
        session._start_recording()
        session.current_frequency_hz = 7200000
        session._submit_transcription()
        self.assertEqual(self.backend.requests[0]['frequency_hz'], 14150000)
        session._handle_transcribing()
        self.assertEqual(session.state, recording.SessionState.COMPLETE)
        self.assertIn('deadline', session.current_result.error)

    def test_broken_result_queue_completes_session_as_failure(self):
        session = self.make_session()
        session._start_recording()
        session._submit_transcription()
        self.backend.get_result = Mock(side_effect=OSError('broken queue'))
        with self.assertLogs(recording.logger, level='ERROR'):
            session._handle_transcribing()
        self.assertEqual(session.state, recording.SessionState.COMPLETE)
        self.assertFalse(session.current_result.success)

    def test_contest_results_use_capture_frequency_and_existing_activity_type(self):
        band_map = station.BandMapState('20m')
        scanner = signals.SignalScanner(band_maps={'20m': band_map}, auto_center_enabled=False)
        scanner.current_frequency = 7200000
        for callsign in ('K1ABC', None):
            with self.subTest(callsign=callsign):
                result = recording.SessionResult(1, frequency_hz=14150000,
                    transcript='CQ contest K1ABC', analysis=NS(is_contest=True,
                    running_station_callsign=callsign, confidence=.9,
                    contest_type='CQWW', exchange_info=None))
                scanner._on_session_result(result)
        self.assertEqual(band_map.stations[0].frequency, 14150000)
        self.assertEqual(band_map.stations[0].activity_type, station.ActivityType.RUN_STATION)

    def test_retuning_during_capture_cancels_mixed_frequency_recording(self):
        radio = Radio()
        scanner = signals.SignalScanner(radio=radio, auto_center_enabled=False)
        session = scanner.recording_session
        session.current_frequency_hz = radio.frequency
        session._start_recording()
        radio.frequency = 7200000
        scanner.start()
        scanner.process_audio(np.zeros(32, dtype=np.float32))
        self.assertIsNone(session.current_result)
        self.assertNotEqual(session.state, recording.SessionState.RECORDING)


if __name__ == '__main__':
    unittest.main()
