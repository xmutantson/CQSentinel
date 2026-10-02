"""Second independent review: fake device boundaries, plus real Qt signal delivery.
Run directly with python -B. No radios, sockets, model loading, or inference.
"""
import logging
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / 'tests')]
from cqsentinel.config import AppConfig, validate_config
from cqsentinel.scanner.profiles import BAND_PROFILES
import test_gui_workflow as gui


class SecondReviewTests(unittest.TestCase):
    def test_all_supported_gui_bands_remain_valid_configuration(self):
        failures = []
        for band in ('6m', '2m', '70cm'):
            self.assertIn(band, BAND_PROFILES)
            candidate = AppConfig()
            candidate.scan.enabled_bands = [band]
            try:
                validate_config(candidate)
            except ValueError as exc:
                failures.append((band, str(exc)))
        self.assertEqual(failures, [], 'Supported GUI/profile bands must survive configuration validation')

    def test_real_reinitialize_does_not_publish_success_when_stream_start_fails(self):
        selected = AppConfig()
        selected.radio.audio_device_name = 'Synthetic B'
        created = []
        def capture(**kwargs):
            item = NS(_recording=False, sample_rate=16000,
                      start_stream=Mock(return_value=False), stop_stream=Mock())
            created.append(item)
            return item
        cls = gui.controller('cqsentinel/gui/main_window.py', 'MainWindow',
            {'show_settings', '_reinitialize_audio_devices', 'start_audio_monitoring'},
            {'SettingsDialog': lambda parent: NS(settings_applied=True, exec=lambda: 0),
             'get_config': lambda: selected, 'QMessageBox': Mock(),
             'AudioCapture': capture,
             'AudioBroadcaster': lambda: NS(register_consumer=Mock()),
             'AudioLevelMeter': lambda: NS(process_chunk=Mock()),
             'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = AppConfig()
        window.config.radio.audio_device_name = 'Synthetic A'
        window.scan_btn = gui.Control(text='Start Scan')
        window.log = Mock()
        window.audio = NS(_recording=True, stop_stream=Mock())
        window.audio_monitor = NS(process_chunk=Mock())
        window.audio_pipeline = None
        window._get_audio_device_index = lambda: 7
        window.show_settings()
        created[0].start_stream.assert_called_once()
        self.assertFalse(created[0]._recording)
        # The complete real method chain reported success despite failed startup.
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic A',
                         'Failed streaming must retain a retryable runtime baseline')

    def test_basic_scan_finishes_through_actual_qt_queued_signals(self):
        from PyQt5.QtCore import QCoreApplication, QObject, QThread, pyqtSignal
        import threading
        app = QCoreApplication.instance() or QCoreApplication([])
        released = threading.Event()
        class SignalOwner(QObject):
            basic_scan_finished_signal = pyqtSignal(object)
        class Worker(QThread):
            log_signal = pyqtSignal(str)
            freq_update_signal = pyqtSignal(int)
            def __init__(self, **kwargs):
                super().__init__()
            def run(self):
                released.wait(2)
            def stop(self):
                released.set()
        cls = gui.controller('cqsentinel/gui/main_window.py', 'MainWindow',
            {'toggle_scan', 'on_scan_finished'},
            {'ScanThread': Worker, 'logger': logging.getLogger(__name__),
             'QMessageBox': Mock()}, base=SignalOwner)
        fixture = gui.GuiScanTests()
        fixture.setUp()
        window = cls()
        window.__dict__.update(fixture.window.__dict__)
        window.use_full_scanner = False
        window.update_freq_display = Mock()
        window.basic_scan_finished_signal.connect(window.on_scan_finished)
        worker = None
        try:
            window.toggle_scan()
            worker = window.scan_thread
            self.assertIsNotNone(worker)
            window.toggle_scan()
            self.assertFalse(window.scan_btn.enabled)
            self.assertIs(window.scan_thread, worker)
            deadline = time.monotonic() + 2
            while window.scan_thread is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
            self.assertIsNone(window.scan_thread)
            self.assertTrue(window.scan_btn.enabled)
            self.assertTrue(window.freq_input.enabled)
            self.assertEqual(window.scan_btn.text(), 'Start Scan')
            newer = Worker()
            window.scan_thread = newer
            window.scan_btn.setText('Stop Scan')
            window.basic_scan_finished_signal.emit(worker)
            app.processEvents()
            self.assertIs(window.scan_thread, newer)
            self.assertEqual(window.scan_btn.text(), 'Stop Scan')
        finally:
            released.set()
            if worker is not None:
                worker.wait(2000)


if __name__ == '__main__':
    unittest.main(defaultTest='SecondReviewTests', verbosity=2)
