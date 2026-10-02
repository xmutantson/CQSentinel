"""Independent final-repair checks: synthetic device/UI boundaries only."""
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / 'tests')]
from cqsentinel.config import AppConfig
import test_gui_workflow as gui


class FinalRepairChecks(unittest.TestCase):
    def window(self, outcomes):
        selected = [AppConfig()]
        selected[0].radio.audio_device_name = 'Synthetic B'
        captures = []
        choices = iter(outcomes)
        def factory(**kwargs):
            outcome = next(choices)
            capture = NS(_recording=False, sample_rate=16000, close=Mock())
            def start(callback):
                if isinstance(outcome, Exception):
                    raise outcome
                capture._recording = outcome is True
                return outcome
            capture.start_stream = Mock(side_effect=start)
            capture.stop_stream = Mock(side_effect=lambda: setattr(capture, '_recording', False))
            captures.append(capture)
            return capture
        cls = gui.controller('cqsentinel/gui/main_window.py', 'MainWindow',
            {'show_settings', '_reinitialize_audio_devices', 'start_audio_monitoring'},
            {'SettingsDialog': lambda parent: NS(settings_applied=True, exec=lambda: 0),
             'get_config': lambda: selected[0], 'QMessageBox': Mock(),
             'AudioCapture': factory,
             'AudioBroadcaster': lambda: NS(register_consumer=Mock()),
             'AudioLevelMeter': lambda: NS(process_chunk=Mock()),
             'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = AppConfig()
        window.config.radio.audio_device_name = 'Synthetic A'
        window.scan_btn = gui.Control(text='Start Scan')
        window.log = Mock()
        old = NS(_recording=True, close=Mock())
        old.stop_stream = Mock(side_effect=lambda: setattr(old, '_recording', False))
        window.audio = old
        window.audio_monitor = NS(process_chunk=Mock())
        window.audio_pipeline = None
        window._get_audio_device_index = lambda: 7 if window.config.radio.audio_device_name == 'Synthetic B' else 4
        return window, selected, captures, old

    def test_reverting_to_original_device_after_failed_swap_restarts_capture(self):
        window, selected, captures, old = self.window([False, True])
        with self.assertLogs(level='WARNING'):
            window.show_settings()
        self.assertFalse(old._recording)
        self.assertFalse(captures[0]._recording)
        self.assertTrue(window._audio_monitoring_requested)
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic A')
        restored = AppConfig()
        restored.radio.audio_device_name = 'Synthetic A'
        selected[0] = restored  # Next dialog Apply chooses original device A.
        window.show_settings()
        self.assertEqual(len(captures), 2,
                         'Original capture A was stopped: choosing A must actually recreate/start it')
        self.assertTrue(window.audio._recording)

    def test_repeated_same_device_failures_remain_retryable_until_success(self):
        window, selected, captures, old = self.window([False, OSError('synthetic'), True])
        for _ in range(2):
            with self.assertLogs(level='WARNING'):
                window.show_settings()
            self.assertEqual(window._applied_audio_devices[0], 'Synthetic A')
            self.assertTrue(window._audio_monitoring_requested)
            self.assertFalse(window.audio._recording)
        window.show_settings()
        self.assertEqual(len(captures), 3)
        self.assertTrue(window.audio._recording)
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic B')
        window.show_settings()
        self.assertEqual(len(captures), 3)


if __name__ == '__main__':
    unittest.main(defaultTest='FinalRepairChecks', verbosity=2)
