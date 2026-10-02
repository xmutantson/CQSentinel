"""Additional benign regressions for failure and ownership boundaries from review."""
import copy
import logging
import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np

from cqsentinel.config import AppConfig
from cqsentinel.speech import subprocess_transcriber as pool
from cqsentinel.speech.router import TranscriptionRouter
import test_config_router as config_fixtures
import test_gui_workflow as gui_fixtures
import test_scan_workflow as scan_fixtures
from test_review_regressions import fm


class ConfigurationValidationTests(unittest.TestCase):
    def setUp(self):
        config_fixtures.ConfigTests.setUp(self)

    def test_semantically_invalid_yaml_preserves_active_config_and_file(self):
        invalid_documents = (
            'radio: {rigctld_port: true}',
            'radio: {rigctld_port: 65536}',
            'radio: {audio_sample_rate: 12345}',
            'radio: {auto_start_rigctld: "false"}',
            'scan: {scan_speed_steps_per_sec: .nan}',
            'scan: {step_size_hz: 0}',
            'scan: {fm_scan_step_hz: 0}',
            'scan: {enabled_bands: "20m"}',
            'scan: {enabled_bands: [20]}',
            'scan: {enabled_bands: [unknown]}',
            'audio: {network_whisper_timeout: .inf}',
            'audio: {gpu_memory_fraction: 1.1}',
            'audio: {whisper_beam_size: 2.5}',
            'audio: {pitch_fmin: 900, pitch_fmax: 100}',
            'audio: {sample_rate: 0}',
            'audio: {noise_reduction_level: unexpected}',
            'audio: {openai_api_key: 123}',
            'band_plan: {band_20m: [14200000]}',
            'band_plan: {band_20m: [14200000, 14100000]}',
            'band_plan: {band_20m: [false, 14200000]}',
            'band_plan: {band_20m: ["14100000", 14200000]}',
            'band_plan: {band_20m: null}',
            'config_dir: []',
            'log_level: 7',
        )
        active = self.manager.config
        active.radio.serial_port = 'Previous active port'
        for document in invalid_documents:
            with self.subTest(document=document):
                self.path.write_text(document, encoding='utf-8')
                with self.assertLogs('cqsentinel.config', level='ERROR'), self.assertRaises(ValueError):
                    self.manager.load()
                self.assertIs(self.manager.config, active)
                self.assertEqual(active.radio.serial_port, 'Previous active port')
                with self.assertRaises(ValueError):
                    self.manager.save()
                self.assertEqual(self.path.read_text(encoding='utf-8'), document)

    def test_invalid_save_does_not_replace_previous_active_or_durable_values(self):
        self.manager.save()
        active = self.manager.config
        original = self.path.read_bytes()
        edited = copy.deepcopy(active)
        edited.scan.step_size_hz = -1
        with self.assertRaises(ValueError):
            self.manager.save(edited)
        self.assertIs(self.manager.config, active)
        self.assertEqual(self.path.read_bytes(), original)


class CaptureAttributionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scan_fixtures.ScanTests()
        self.scanner = self.fixture.make_scanner()

    def test_successful_tune_with_wrong_readback_cannot_publish_audio(self):
        self.fixture.radio.get_frequency = Mock(return_value=14_000_000)
        self.scanner._process_frequency(14_150_000)
        self.assertEqual(self.fixture.backend.requests, [])
        self.assertEqual(self.fixture.band_map.stations, [])

    def test_rejected_centering_tune_cannot_publish_requested_center(self):
        original_tune = self.fixture.radio.set_frequency
        def tune(frequency):
            if frequency != 14_150_000:
                return False
            return original_tune(frequency)
        self.fixture.radio.set_frequency = tune
        self.scanner.auto_center_enabled = True
        def center(radio, capture, frequency, **kwargs):
            radio.set_frequency(frequency + 100)
            raise AssertionError('A failed centering CAT command must abort')
        self.scanner.tuner = NS(set_sideband=Mock(), auto_center=center)
        self.scanner._process_frequency(14_150_000)
        self.assertEqual(self.fixture.backend.requests, [])

    def test_rejected_fm_fallback_aborts_capture(self):
        self.fixture.radio.mode = 'FM'
        self.scanner.auto_center_enabled = True
        self.scanner.fm_tuner = fm.FMAutoTuner()
        original_tune = self.fixture.radio.set_frequency
        attempts = []
        def tune(frequency):
            attempts.append(frequency)
            if len(attempts) > 1:
                return False
            return original_tune(frequency)
        self.fixture.radio.set_frequency = tune
        with patch.object(fm.time, 'sleep', return_value=None):
            self.scanner._process_frequency(146_520_000)
        self.assertEqual(self.fixture.backend.requests, [])

    def test_fm_mode_restore_failure_aborts_capture(self):
        self.fixture.radio.mode = 'FM'
        self.scanner.auto_center_enabled = True
        self.scanner.fm_tuner = fm.FMAutoTuner(scan_range_hz=100)
        original_mode = self.fixture.radio.set_mode
        def mode(value, bandwidth):
            if value == 'FM':
                return False
            return original_mode(value, bandwidth)
        self.fixture.radio.set_mode = mode
        with patch.object(fm.time, 'sleep', return_value=None):
            self.scanner._process_frequency(146_520_000)
        self.assertEqual(self.fixture.backend.requests, [])


class SubmissionAndRecoveryTests(unittest.TestCase):
    def backend(self):
        with patch.object(pool.mp, 'Queue', side_effect=lambda **kwargs: queue.Queue(**kwargs)):
            backend = pool.SubprocessTranscriber(num_workers=1)
        backend.is_ready = True
        backend.workers = [NS(pid=1, is_alive=lambda: True)]
        backend.worker_ids = [0]
        def cleanup():
            backend._shutting_down = True
            backend.workers = []
        self.addCleanup(cleanup)
        return backend

    def test_cancel_during_submission_does_not_wait_for_backend_and_fast_result_is_retained(self):
        backend = config_fixtures.FakeBackend()
        router = TranscriptionRouter(backend)
        old = router.transcribe_async(audio=[])
        entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
        original = backend.transcribe_async
        def submit(**kwargs):
            request = original(**kwargs)
            backend.results.put(NS(request_id=request, text='immediate'))
            entered.set()
            release.wait(2)
            return request
        backend.transcribe_async = submit
        ids = []
        submit_thread = threading.Thread(target=lambda: ids.append(router.transcribe_async(audio=[])))
        cancel_thread = threading.Thread(target=lambda: (router.cancel(old), cancelled.set()))
        submit_thread.start()
        try:
            self.assertTrue(entered.wait(1))
            cancel_thread.start()
            self.assertTrue(cancelled.wait(.5), 'cancel must not wait on the submission lock')
            self.assertIsNone(router.get_result_for(old))
        finally:
            release.set()
            submit_thread.join(2)
            if cancel_thread.ident is not None:
                cancel_thread.join(2)
        self.assertEqual(router.get_result_for(ids[0]).text, 'immediate')

    def test_new_submission_drains_abandoned_results_after_full_queue_rejection(self):
        backend = self.backend()
        router = TranscriptionRouter(backend)
        old = router.transcribe_async(audio=np.zeros(8), sample_rate=16000)
        router.cancel(old)
        backend.output_queue.put(pool.TranscriptionResult(old, 'late', True))
        current = router.transcribe_async(audio=np.zeros(8), sample_rate=16000)
        self.assertTrue(backend.output_queue.empty())
        self.assertEqual(router._pending, {current})
        self.assertEqual(router._results, {})

    def test_full_queue_rejection_leaves_no_orphan_router_ownership(self):
        backend = self.backend()
        backend.input_queue = queue.Queue(maxsize=1)
        router = TranscriptionRouter(backend)
        first = router.transcribe_async(audio=np.zeros(8), sample_rate=16000)
        with self.assertRaisesRegex(RuntimeError, 'queue full'):
            router.transcribe_async(audio=np.zeros(8), sample_rate=16000)
        self.assertEqual(router._pending, {first})
        self.assertFalse(router._submitting)
        self.assertEqual(backend.input_queue.qsize(), 1)

    def test_recovery_queue_clear_reports_failure_to_request_owner(self):
        backend = self.backend()
        router = TranscriptionRouter(backend)
        request_id = router.transcribe_async(audio=np.zeros(8), sample_rate=16000)
        self.assertEqual(backend.clear_input_queue(), 1)
        result = router.get_result_for(request_id)
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIn('recovery', result.error)

    def test_respawn_does_not_wait_for_or_consume_readiness(self):
        backend = self.backend()
        backend.workers = [NS(pid=1, is_alive=lambda: False)]
        backend.output_queue = Mock()
        replacement = NS(pid=2, is_alive=lambda: True, start=Mock())
        with patch.object(pool.mp, 'Process', return_value=replacement):
            self.assertEqual(backend.respawn_dead_workers(), 1)
        backend.output_queue.get.assert_not_called()
        backend.output_queue.get_nowait.assert_not_called()
        replacement.start.assert_called_once()

    def test_readiness_before_transcript_is_dispatched_separately(self):
        backend = self.backend()
        router = TranscriptionRouter(backend)
        request_id = router.transcribe_async(audio=np.zeros(8), sample_rate=16000)
        backend.output_queue.put(pool.TranscriptionResult(-1, '', True, worker_id=0))
        backend.output_queue.put(pool.TranscriptionResult(request_id, 'CQ', True))
        self.assertEqual(router.get_result_for(request_id).text, 'CQ')
        self.assertEqual(backend.workers_ready, 1)


class BasicOwnershipTests(unittest.TestCase):
    def setUp(self):
        fixture = gui_fixtures.GuiScanTests()
        fixture.setUp()
        self.window = fixture.window
        self.window.use_full_scanner = False
        self.window.scan_btn.setText('Stop Scan')
        self.window.freq_input.setEnabled(False)
        self.window.connect_btn.setEnabled(False)
        self.worker = NS(stop=Mock(), wait=Mock(), isRunning=lambda: True)
        self.window.scan_thread = self.worker

    def test_stop_returns_without_wait_then_identity_completion_releases_controls(self):
        window = self.window
        window.toggle_scan()
        self.worker.stop.assert_called_once()
        self.worker.wait.assert_not_called()
        self.assertIs(window.scan_thread, self.worker)
        self.assertFalse(window.freq_input.enabled)
        window.on_scan_finished(self.worker)
        self.assertIsNone(window.scan_thread)
        self.assertTrue(window.freq_input.enabled)
        self.assertTrue(window.connect_btn.enabled)
        self.assertTrue(window.scan_btn.enabled)
        self.assertEqual(window.scan_btn.text(), 'Start Scan')

    def test_close_defers_until_identity_completion(self):
        event = Mock()
        self.window.closeEvent(event)
        event.ignore.assert_called_once()
        self.worker.wait.assert_not_called()
        self.window.audio.stop_stream.assert_not_called()
        self.window.close.assert_not_called()
        self.window.on_scan_finished(self.worker)
        self.window.close.assert_called_once()

    def test_explicit_old_worker_completion_does_not_unlock_new_owner(self):
        old = NS()
        self.window.on_scan_finished(old)
        self.assertIs(self.window.scan_thread, self.worker)
        self.assertFalse(self.window.freq_input.enabled)
        self.assertEqual(self.window.scan_btn.text(), 'Stop Scan')


class DeviceRetryTests(unittest.TestCase):
    def test_failed_reinitialization_can_retry_same_saved_device_until_success(self):
        selected = AppConfig()
        selected.radio.audio_device_name = 'Synthetic B'
        cls = gui_fixtures.controller('cqsentinel/gui/main_window.py', 'MainWindow', {'show_settings'},
            {'SettingsDialog': lambda parent: NS(settings_applied=True, exec=lambda: 0),
             'get_config': lambda: selected, 'QMessageBox': Mock(),
             'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = AppConfig()
        window.config.radio.audio_device_name = 'Synthetic A'
        window.scan_btn = gui_fixtures.Control(text='Start Scan')
        window.log = Mock()
        window._reinitialize_audio_devices = Mock(side_effect=[False, True])
        window.show_settings()
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic A')
        window.show_settings()
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic B')
        window.show_settings()
        self.assertEqual(window._reinitialize_audio_devices.call_count, 2)


if __name__ == '__main__':
    unittest.main()
