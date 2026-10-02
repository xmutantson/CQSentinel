"""Independent offline assertions for expected reliability, originally failed on reviewed HEAD 5e4fb8d.
Run directly with python -B or through unittest discovery. No real devices, worker
processes, sockets, model construction, or inference. Scratch/config files remain on D.
"""
import copy
import importlib.util
import logging
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / 'tests')]
from cqsentinel.config import AppConfig, ConfigManager
from cqsentinel.speech.router import TranscriptionRouter
from cqsentinel.speech import subprocess_transcriber as pool
from test_gui_workflow import controller, Control, GuiScanTests
from test_scan_workflow import ScanTests
from offline_modules import engine

spec = importlib.util.spec_from_file_location('review_real_fm', REPO / 'cqsentinel/radio/fm_tuner.py')
fm = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fm
spec.loader.exec_module(fm)


class IndependentReviewTests(unittest.TestCase):
    def scanner(self):
        fixture = ScanTests()
        scanner = fixture.make_scanner()
        return scanner, fixture

    def test_successful_real_fm_centering_reaches_transcription(self):
        scanner, f = self.scanner()
        f.radio.mode = 'FM'
        scanner.auto_center_enabled = True
        scanner.fm_tuner = fm.FMAutoTuner()
        with patch.object(fm.time, 'sleep', return_value=None):
            scanner._process_frequency(146_520_000)
        self.assertEqual(len(f.backend.requests), 1,
                         'Successful FM centering must reach capture/transcription')

    def test_failed_fm_centering_preserves_capture_frequency(self):
        scanner, f = self.scanner()
        f.radio.mode = 'FM'
        scanner.auto_center_enabled = True
        scanner.fm_tuner = fm.FMAutoTuner()
        capture_frequencies = []
        def record(duration, cancel_requested=None):
            if duration == .2:  # silent edge checks make centering fail
                return np.zeros(3200, dtype=np.float32)
            capture_frequencies.append(f.radio.frequency)
            return np.ones(int(duration * 16000), dtype=np.float32)
        f.audio.record = record
        with patch.object(fm.time, 'sleep', return_value=None):
            scanner._process_frequency(146_520_000)
        self.assertEqual(len(f.backend.requests), 1)
        self.assertEqual(f.backend.requests[0]['frequency_hz'], capture_frequencies[0],
                         'Metadata must match the frequency actually captured')

    def test_failed_cat_tune_does_not_attribute_old_audio_to_requested_frequency(self):
        scanner, f = self.scanner()
        f.radio.frequency = 14_150_000
        # Real HamlibController.set_frequency returns False on connection error.
        f.radio.set_frequency = Mock(return_value=False)
        with patch.object(engine.time, 'sleep', return_value=None):
            scanner._process_frequency(14_200_000)
        self.assertEqual(len(f.backend.requests), 0,
                         'A rejected CAT tune must prevent recording under the requested frequency')

    def test_worker_respawn_preserves_completed_results_for_router(self):
        # Real pool methods; replace process/IPC boundaries with ordinary queues/fakes.
        with patch.object(pool.mp, 'Queue', side_effect=lambda **kwargs: queue.Queue()):
            backend = pool.SubprocessTranscriber(num_workers=2)
        backend.is_ready = True
        backend.workers = [NS(pid=1, is_alive=lambda: False), NS(pid=2, is_alive=lambda: True)]
        backend.worker_ids = [0, 1]
        backend._last_respawn_time = 0
        backend._respawn_cooldown = 0
        router = TranscriptionRouter(backend)
        request_id = router.transcribe_async(audio=np.ones(16), sample_rate=16000, frequency_hz=14150000)
        backend.output_queue.put(pool.TranscriptionResult(request_id, 'CQ K1ABC', True))
        def fake_process(**kwargs):
            worker_id = kwargs['args'][0]
            return NS(pid=3, is_alive=lambda: True,
                      start=lambda: backend.output_queue.put(
                          pool.TranscriptionResult(-1, '', True, worker_id=worker_id)))
        try:
            with patch.object(pool.mp, 'Process', side_effect=fake_process):
                self.assertEqual(backend.respawn_dead_workers(), 1)
            self.assertIsNotNone(router.get_result_for(request_id),
                                 'Worker recovery consumed and discarded an owned result')
        finally:
            backend._shutting_down = True
            backend.workers = []

    def test_malformed_known_config_field_is_rejected_before_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            path.write_text('radio:\n  rigctld_port: not-a-number\n', encoding='utf-8')
            manager = ConfigManager(str(path))
            with self.assertRaises((ValueError, TypeError),
                                   msg='Known typed fields need validation, not just mapping validation'):
                manager.load()

    def test_blocked_device_apply_can_be_retried_after_stopping(self):
        selected = AppConfig()
        selected.radio.audio_device_name = 'Synthetic input B'
        messages = Mock()
        cls = controller('cqsentinel/gui/main_window.py', 'MainWindow', {'show_settings'},
                         {'SettingsDialog': lambda parent: NS(settings_applied=True, exec=lambda: 0),
                          'get_config': lambda: selected, 'QMessageBox': messages,
                          'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = AppConfig()
        window.config.radio.audio_device_name = 'Synthetic input A'
        window.scan_btn = Control(text='Stop Scan')
        window.log = Mock()
        window._reinitialize_audio_devices = Mock()
        window.show_settings()  # successful Apply + Cancel while scan active
        messages.warning.assert_called_once()
        window._reinitialize_audio_devices.assert_not_called()
        window.scan_btn.setText('Start Scan')
        window.show_settings()  # reopen and Apply the already selected B
        window._reinitialize_audio_devices.assert_called_once()

    def test_basic_stop_wait_timeout_keeps_ownership_and_controls_locked(self):
        fixture = GuiScanTests()
        fixture.setUp()
        window = fixture.window
        window.use_full_scanner = False
        window.scan_btn.setText('Stop Scan')
        window.freq_input.setEnabled(False)
        window.connect_btn.setEnabled(False)
        worker = NS(stop=Mock(), wait=Mock(return_value=False), isRunning=lambda: True)
        window.scan_thread = worker
        window.toggle_scan()
        self.assertFalse(window.freq_input.enabled,
                         'Timed-out basic worker can still tune; manual control must stay locked')
        self.assertFalse(window.scan_btn.enabled)

    def test_basic_delayed_finished_signal_does_not_release_new_scan(self):
        fixture = GuiScanTests()
        fixture.setUp()
        window = fixture.window
        window.use_full_scanner = False
        window.scan_btn.setText('Stop Scan')
        old_worker = NS(stop=Mock(), wait=Mock(return_value=True))
        window.scan_thread = old_worker
        window.toggle_scan()  # synchronous wait ends before queued Qt finished delivery
        new_worker = NS(isRunning=lambda: True)
        window.scan_thread = new_worker
        window.scan_btn.setText('Stop Scan')
        window.on_scan_finished()  # old worker's queued signal has no identity argument
        self.assertIs(window.scan_thread, new_worker,
                      'An old basic-worker completion must not release the new owner')

    def test_stop_interrupts_submission_to_full_local_queue(self):
        scanner, f = self.scanner()
        with patch.object(pool.mp, 'Queue', side_effect=lambda **kwargs: queue.Queue()):
            backend = pool.SubprocessTranscriber(num_workers=1)
        backend.is_ready = True
        backend.workers = [NS(pid=1, is_alive=lambda: True)]
        backend.worker_ids = [0]
        entered = threading.Event()
        class FullQueue(queue.Queue):
            def put(self, item, *args, **kwargs):
                entered.set()
                return super().put(item, *args, **kwargs)
        backend.input_queue = FullQueue(maxsize=1)
        queue.Queue.put(backend.input_queue, object())
        scanner.transcriber = TranscriptionRouter(backend)
        worker = threading.Thread(target=scanner._process_frequency, args=(14150000,), daemon=True)
        scanner._scan_thread = worker
        worker.start()
        try:
            self.assertTrue(entered.wait(2), 'Submission reached full queue')
            scanner.stop_scan()
            self.assertTrue(scanner.wait_stopped(.2),
                            'Stop cannot finish while transcribe_async blocks in queue.put')
        finally:
            backend.input_queue.get_nowait()  # release fake queue, never leave a test thread blocked
            worker.join(2)
            backend._shutting_down = True
            backend.workers = []
    def test_skip_during_capture_discards_request_and_next_frequency_works(self):
        scanner, f = self.scanner()
        original = f.audio.record
        def skip_during_capture(duration, cancel_requested=None):
            scanner.skip_current()
            return original(duration, cancel_requested)
        f.audio.record = skip_during_capture
        with patch.object(engine.time, 'sleep', return_value=None):
            scanner._process_frequency(14150000)
            self.assertEqual(f.backend.requests, [])
            f.audio.record = original
            scanner._process_frequency(14200000)
        self.assertEqual(len(f.backend.requests), 1)
        self.assertEqual(f.backend.requests[0]['frequency_hz'], 14200000)


def load_tests(loader, tests, pattern):
    # Imported fixture classes are helpers, not duplicate suite entries.
    return loader.loadTestsFromTestCase(IndependentReviewTests)


if __name__ == '__main__':
    unittest.main(defaultTest='IndependentReviewTests', verbosity=2)

