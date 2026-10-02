"""Audio replacement state transitions through the real three-method chain."""
import logging
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

from cqsentinel.config import AppConfig
import test_gui_workflow as gui


class AudioRecoveryTransitions(unittest.TestCase):
    def window(self, outcomes, active=True):
        selected = [AppConfig()]
        selected[0].radio.audio_device_name = 'B'
        captures = []
        attempts = []
        outcomes = iter(outcomes)
        dialog = NS(settings_applied=True, exec=lambda: 0)
        messages = Mock()
        def factory(**kwargs):
            outcome = next(outcomes)
            attempts.append(kwargs['device'])
            if outcome == 'construction failure':
                raise OSError('synthetic construction failure')
            capture = NS(_recording=False, device=kwargs['device'],
                         sample_rate=16000, close=Mock())
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
            {'SettingsDialog': lambda parent: dialog, 'get_config': lambda: selected[0],
             'QMessageBox': messages, 'AudioCapture': factory,
             'AudioBroadcaster': lambda: NS(register_consumer=Mock()),
             'AudioLevelMeter': lambda: NS(process_chunk=Mock()),
             'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = AppConfig()
        window.config.radio.audio_device_name = 'A'
        window.scan_btn = gui.Control(text='Start Scan')
        window.log = Mock()
        original = NS(_recording=active, device=1, close=Mock())
        original.stop_stream = Mock(side_effect=lambda: setattr(original, '_recording', False))
        window.audio = original
        window.audio_monitor = NS(process_chunk=Mock())
        window.audio_pipeline = None
        window._get_audio_device_index = lambda: {'A': 1, 'B': 2, 'C': 3}[window.config.radio.audio_device_name]
        return NS(window=window, selected=selected, captures=captures, attempts=attempts,
                  original=original, dialog=dialog, messages=messages)

    def select(self, fixture, device):
        fixture.selected[0] = AppConfig()
        fixture.selected[0].radio.audio_device_name = device

    def test_failure_then_return_retry_or_new_device_recovers_and_becomes_noop(self):
        # Each failed replacement must recover for A (last success), B (retry),
        # or C (new choice), independent of where initialization failed.
        for failure in ('construction failure', False, OSError('synthetic start failure')):
            for choice, device_index in (('A', 1), ('B', 2), ('C', 3)):
                with self.subTest(failure=str(failure), choice=choice):
                    f = self.window([failure, True])
                    with self.assertLogs(level='WARNING'):
                        f.window.show_settings()
                    self.assertFalse(f.original._recording)
                    f.original.close.assert_called_once()
                    self.assertTrue(f.window._audio_devices_pending)
                    self.assertTrue(f.window._audio_monitoring_requested)
                    self.assertEqual(f.window._applied_audio_devices[0], 'A')
                    f.messages.critical.assert_called_once()
                    self.select(f, choice)
                    f.window.show_settings()
                    self.assertEqual(f.attempts, [2, device_index])
                    self.assertIs(f.window.audio, f.captures[-1])
                    self.assertTrue(f.window.audio._recording)
                    f.window.audio.start_stream.assert_called_once()
                    self.assertFalse(f.window._audio_devices_pending)
                    self.assertEqual(f.window._applied_audio_devices[0], choice)
                    f.window.show_settings()
                    self.assertEqual(len(f.attempts), 2, 'Successful repeated Apply should be a no-op')

    def test_selection_changes_and_repeated_failures_keep_pending_until_success(self):
        f = self.window([False, OSError('synthetic A start failure'), True])
        for choice in ('B', 'A'):
            self.select(f, choice)
            with self.assertLogs(level='WARNING'):
                f.window.show_settings()
            self.assertTrue(f.window._audio_devices_pending)
            self.assertFalse(f.window.audio._recording)
            self.assertEqual(f.window._applied_audio_devices[0], 'A')
        self.select(f, 'C')
        f.window.show_settings()
        self.assertEqual(f.attempts, [2, 1, 3])
        self.assertTrue(f.window.audio._recording)
        self.assertFalse(f.window._audio_devices_pending)
        self.assertEqual(f.window._applied_audio_devices[0], 'C')

    def test_blocked_and_cancelled_apply_retain_pending_then_original_device_recovers(self):
        f = self.window([False, True])
        with self.assertLogs(level='WARNING'):
            f.window.show_settings()
        self.select(f, 'A')
        f.window.scan_btn.setText('Stop Scan')
        f.window.show_settings()
        f.messages.warning.assert_called_once()
        self.assertEqual(f.attempts, [2])
        self.assertTrue(f.window._audio_devices_pending)
        f.window.scan_btn.setText('Start Scan')
        f.dialog.settings_applied = False  # Close without saving/applying.
        f.window.show_settings()
        self.assertEqual(f.attempts, [2])
        self.assertTrue(f.window._audio_devices_pending)
        f.dialog.settings_applied = True
        f.window.show_settings()
        self.assertEqual(f.attempts, [2, 1])
        self.assertTrue(f.window.audio._recording)
        self.assertFalse(f.window._audio_devices_pending)

    def test_blocked_change_does_not_invalidate_original_capture(self):
        f = self.window([])
        f.window.scan_btn.setText('Stop Scan')
        f.window.show_settings()  # B was never actually attempted.
        f.messages.warning.assert_called_once()
        self.assertTrue(f.original._recording)
        self.assertFalse(getattr(f.window, '_audio_devices_pending', False))
        self.select(f, 'A')
        f.window.scan_btn.setText('Start Scan')
        f.window.show_settings()
        self.assertEqual(f.attempts, [])
        self.assertIs(f.window.audio, f.original)
        self.assertTrue(f.original._recording)
        f.original.stop_stream.assert_not_called()

    def test_inactive_capture_construction_failure_recovers_without_starting_monitoring(self):
        f = self.window(['construction failure', True], active=False)
        with self.assertLogs(level='WARNING'):
            f.window.show_settings()
        self.assertTrue(f.window._audio_devices_pending)
        self.assertFalse(f.window._audio_monitoring_requested)
        self.select(f, 'A')
        f.window.show_settings()
        self.assertEqual(f.attempts, [2, 1])
        self.assertFalse(f.window.audio._recording)
        f.window.audio.start_stream.assert_not_called()
        self.assertFalse(f.window._audio_devices_pending)
        f.window.show_settings()
        self.assertEqual(len(f.attempts), 2)


if __name__ == '__main__':
    unittest.main()
