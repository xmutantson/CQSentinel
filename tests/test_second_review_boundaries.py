"""Exercise second-review fixes through persistence and real controller methods."""
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

from cqsentinel.config import AppConfig, ConfigManager, validate_config
from cqsentinel.scanner.profiles import BAND_PROFILES, SUPPORTED_SCAN_BANDS, ALL_BANDS
import test_gui_workflow as gui


class SupportedBandsTests(unittest.TestCase):
    def test_all_selectable_bands_round_trip_load_and_save(self):
        self.assertEqual(SUPPORTED_SCAN_BANDS,
                         ('160m', '80m', '40m', '20m', '15m', '10m', '6m', '2m', '70cm'))
        self.assertEqual(list(SUPPORTED_SCAN_BANDS), ALL_BANDS.bands)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            manager = ConfigManager(str(path))
            self.assertEqual(manager.get_bands_list(), list(SUPPORTED_SCAN_BANDS))
            for band in SUPPORTED_SCAN_BANDS:
                with self.subTest(band=band):
                    self.assertEqual(BAND_PROFILES[band].band_name, band)
                    candidate = AppConfig()
                    candidate.scan.enabled_bands = [band]
                    manager.save(candidate)
                    loaded = ConfigManager(str(path)).load()
                    self.assertEqual(loaded.scan.enabled_bands, [band])
                    self.assertEqual(loaded.band_plan, candidate.band_plan)

    def test_existing_vhf_uhf_yaml_loads_and_preserves_future_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            path.write_text('scan:\n  enabled_bands: [6m, 2m, 70cm]\n  future_setting: keep\n',
                            encoding='utf-8')
            manager = ConfigManager(str(path))
            self.assertEqual(manager.load().scan.enabled_bands, ['6m', '2m', '70cm'])
            manager.save()
            self.assertIn('future_setting: keep', path.read_text(encoding='utf-8'))
            self.assertEqual(ConfigManager(str(path)).load().scan.enabled_bands,
                             ['6m', '2m', '70cm'])

    def test_unknown_and_non_string_bands_remain_invalid(self):
        for bands in (['unknown'], [False], [2], ['2m', 'not-a-band'], '2m'):
            with self.subTest(bands=bands):
                candidate = AppConfig()
                candidate.scan.enabled_bands = bands
                with self.assertRaises(ValueError):
                    validate_config(candidate)


class AudioStartupChainTests(unittest.TestCase):
    def window(self, outcomes, active=True, desired=False):
        selected = AppConfig()
        selected.radio.audio_device_name = 'Synthetic B'
        captures = []
        results = iter(outcomes)
        def factory(**kwargs):
            outcome = next(results)
            if outcome == 'construction failure':
                raise OSError('synthetic capture construction failure')
            item = NS(_recording=False, sample_rate=16000, close=Mock())
            def start(callback):
                if isinstance(outcome, Exception):
                    raise outcome
                item._recording = outcome is True
                return outcome
            def stop():
                item._recording = False
            item.start_stream = Mock(side_effect=start)
            item.stop_stream = Mock(side_effect=stop)
            captures.append(item)
            return item
        messages = Mock()
        cls = gui.controller('cqsentinel/gui/main_window.py', 'MainWindow',
            {'show_settings', '_reinitialize_audio_devices', 'start_audio_monitoring'},
            {'SettingsDialog': lambda parent: NS(settings_applied=True, exec=lambda: 0),
             'get_config': lambda: selected, 'QMessageBox': messages,
             'AudioCapture': factory,
             'AudioBroadcaster': lambda: NS(register_consumer=Mock()),
             'AudioLevelMeter': lambda: NS(process_chunk=Mock()),
             'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = AppConfig()
        window.config.radio.audio_device_name = 'Synthetic A'
        window.scan_btn = gui.Control(text='Start Scan')
        window.log = Mock()
        old = NS(_recording=active, close=Mock())
        old.stop_stream = Mock(side_effect=lambda: setattr(old, '_recording', False))
        window.audio = old
        window._audio_monitoring_requested = desired
        window.audio_monitor = NS(process_chunk=Mock())
        window.audio_pipeline = None
        window._get_audio_device_index = lambda: 7
        return window, captures, messages, old

    def test_start_failure_or_exception_retries_same_saved_device_and_restarts_monitoring(self):
        for failure in (False, OSError('synthetic stream start failure')):
            with self.subTest(failure=type(failure).__name__):
                window, captures, messages, old = self.window([failure, True])
                with self.assertLogs(level='WARNING'):
                    window.show_settings()
                old.stop_stream.assert_called_once()
                captures[0].start_stream.assert_called_once()
                self.assertFalse(captures[0]._recording)
                self.assertEqual(window.config.radio.audio_device_name, 'Synthetic B')
                self.assertEqual(window._applied_audio_devices[0], 'Synthetic A')
                self.assertTrue(window._audio_monitoring_requested)
                messages.critical.assert_called_once()
                self.assertNotIn('Audio devices hot-swapped successfully!',
                                 [call.args[0] for call in window.log.call_args_list])
                window.show_settings()  # No selection change: same persisted B.
                self.assertEqual(len(captures), 2)
                captures[1].start_stream.assert_called_once()
                self.assertTrue(captures[1]._recording)
                self.assertEqual(window._applied_audio_devices[0], 'Synthetic B')
                window.show_settings()
                self.assertEqual(len(captures), 2, 'Successful Apply must not retry again')

    def test_capture_construction_failure_preserves_monitoring_intent_for_retry(self):
        window, captures, messages, old = self.window(['construction failure', True])
        with self.assertLogs(level='ERROR'):
            window.show_settings()
        self.assertFalse(old._recording)
        self.assertTrue(window._audio_monitoring_requested)
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic A')
        window.show_settings()
        self.assertEqual(len(captures), 1)
        captures[0].start_stream.assert_called_once()
        self.assertTrue(captures[0]._recording)
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic B')

    def test_previously_requested_monitoring_restarts_even_if_old_capture_inactive(self):
        window, captures, messages, old = self.window([True], active=False, desired=True)
        window.show_settings()
        captures[0].start_stream.assert_called_once()
        self.assertTrue(captures[0]._recording)
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic B')

    def test_inactive_unrequested_monitoring_stays_inactive_on_device_change(self):
        window, captures, messages, old = self.window([True], active=False)
        window.show_settings()
        captures[0].start_stream.assert_not_called()
        self.assertFalse(captures[0]._recording)
        self.assertFalse(window._audio_monitoring_requested)
        self.assertEqual(window._applied_audio_devices[0], 'Synthetic B')

    def test_monitor_start_reports_missing_and_already_active_capture(self):
        window, captures, messages, old = self.window([])
        self.assertTrue(window.start_audio_monitoring())
        self.assertTrue(window._audio_monitoring_requested)
        window.audio = None
        self.assertFalse(window.start_audio_monitoring())
        self.assertTrue(window._audio_monitoring_requested)


if __name__ == '__main__':
    unittest.main()
