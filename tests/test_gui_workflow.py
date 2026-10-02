"""Offline GUI controller tests; no Qt window, audio device, or service is opened.

Compile the actual controller methods with fake UI boundaries. This verifies their
behavior and the real BandScanner constructor contract, not Qt rendering/signals.
"""
import ast
import copy
import importlib.util
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cqsentinel.config import AppConfig, ConfigManager
from cqsentinel.scanner.engine import BandScanner

ROOT = Path(__file__).resolve().parents[1]


def controller(relative, class_name, method_names, namespace, base=object):
    source = ast.parse((ROOT / relative).read_text(encoding='utf-8-sig'))
    original = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    methods = [copy.deepcopy(node) for node in original.body
               if isinstance(node, ast.FunctionDef) and node.name in method_names]
    if {node.name for node in methods} != set(method_names):
        raise AssertionError('Requested controller methods not found')
    for method in methods:
        method.decorator_list = []
    cls = ast.ClassDef(name=class_name, bases=[ast.Name(id='BoundaryBase', ctx=ast.Load())],
                       keywords=[], body=methods, decorator_list=[])
    namespace = dict(namespace, BoundaryBase=base)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 str(ROOT / relative), 'exec'), namespace)
    return namespace[class_name]


def station_model():
    # Loading this data-only file avoids importing the bandmap package's Qt widgets.
    name = '_gui_workflow_station_model'
    spec = importlib.util.spec_from_file_location(name, ROOT / 'cqsentinel/bandmap/station.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.BandMapState


class Control:
    def __init__(self, text='', data=None, value=0, checked=False):
        self.label, self.data, self.number, self.checked = text, data, value, checked
        self.enabled = True
        self.scanning = False

    def text(self): return self.label
    def currentText(self): return self.label
    def currentData(self): return self.data
    def value(self): return self.number
    def isChecked(self): return self.checked
    def setText(self, text): self.label = text
    def setEnabled(self, enabled): self.enabled = enabled
    def set_scanning_active(self, active): self.scanning = active


class Signal:
    def __init__(self): self.calls = []
    def emit(self, *args): self.calls.append(args)


class FakeScanner(BandScanner):
    """Retain the real constructor; substitute only worker/hardware execution."""
    def start_scan(self, **kwargs):
        self.active = True
        self.started = kwargs

    def is_scanning(self): return getattr(self, 'active', False)
    def wait_stopped(self, timeout=None): return not self.is_scanning()


class GuiScanTests(unittest.TestCase):
    def setUp(self):
        self.threads = []
        owner = self

        class ThreadBoundary:
            def __init__(self, target, daemon): self.target = target
            def start(self): owner.threads.append(self)

        profiles = {
            '20m': SimpleNamespace(name='20m', freq_start=14150000, freq_end=14151000, step_size=1000),
            '40m': SimpleNamespace(name='40m', freq_start=7125000, freq_end=7126000, step_size=1000),
        }
        cls = controller('cqsentinel/gui/main_window.py', 'MainWindow',
                         {'toggle_scan', '_start_next_band_scan', '_on_band_scan_complete', 'on_scan_finished', 'closeEvent'},
                         {'logger': logging.getLogger(__name__), 'BandScanner': FakeScanner,
                          'BAND_PROFILES': profiles, 'QMessageBox': Mock(),
                          'threading': SimpleNamespace(Thread=ThreadBoundary)})
        self.window = cls()
        w = self.window
        w.config = AppConfig()
        w.config.scan.dwell_with_voice_sec = 12
        w.config.scan.auto_center_enabled = False
        w.config.contest.contestness_threshold = 83
        w.radio = SimpleNamespace(is_connected=True)
        w.audio = Mock()
        w.audio_pipeline = object()
        w.auto_tuner = object()
        w.fm_tuner = object()
        w.transcription_router = object()
        w.callsign_extractor = object()
        w.behavior_analyzer = object()
        w.n3fjp_client = object()
        w.use_full_scanner = True
        w.signal_scanner = Mock()
        w.scan_thread = None
        w.band_scanner = None
        w._scan_stopping = False
        w._close_after_scan = False
        w.scan_btn = Control(text='Start Scan')
        w.skip_btn = Control()
        w.connect_btn = Control()
        w.freq_input = Control()
        w.band_checkboxes = {name: Control(checked=True) for name in profiles}
        model = station_model()
        w.band_maps = {name: model(name) for name in profiles}
        w.band_map_widgets = {name: Control() for name in profiles}
        for name in ('station_detected_signal', 'progress_update_signal', 'scan_finished_signal', 'band_scan_finished_signal'):
            setattr(w, name, Signal())
        w.log = Mock()
        w.update_scan_status = Mock()
        w.close = Mock()

    def test_start_two_bands_uses_selected_backend_and_ignores_old_completion(self):
        w = self.window
        w.toggle_scan()
        first = w.band_scanner
        self.assertIs(first.transcriber, w.transcription_router)
        self.assertIs(first.band_map, w.band_maps['40m'])
        self.assertIsNone(first.n3fjp)
        self.assertEqual(first.dwell_with_voice, 12)
        self.assertFalse(first.auto_center_enabled)
        self.assertEqual(first.min_contestness, 83)
        self.assertFalse(w.freq_input.enabled)
        w.signal_scanner.stop.assert_called_once()
        first.active = False
        w._on_band_scan_complete(first)
        second = w.band_scanner
        self.assertIs(second.band_map, w.band_maps['20m'])
        w._on_band_scan_complete(first)
        self.assertIs(w.band_scanner, second)
        self.assertEqual(len(self.threads), 2)
        self.threads[0].target()
        self.assertEqual(w.band_scan_finished_signal.calls, [(first,)])

    def test_stop_keeps_controls_locked_until_actual_worker_completion(self):
        w = self.window
        w.toggle_scan()
        scanner = w.band_scanner
        w.toggle_scan()
        self.assertTrue(scanner._stop_requested)
        self.assertTrue(scanner.is_scanning())
        self.assertIs(w.band_scanner, scanner)
        self.assertFalse(w.scan_btn.enabled)
        self.assertFalse(w.freq_input.enabled)
        scanner.active = False
        w._on_band_scan_complete(scanner)
        self.assertIsNone(w.band_scanner)
        self.assertEqual(w.scan_btn.text(), 'Start Scan')
        self.assertTrue(w.scan_btn.enabled)
        self.assertTrue(w.freq_input.enabled)
        self.assertTrue(w.connect_btn.enabled)
        self.assertEqual(len(self.threads), 1)

    def test_close_defers_dependency_shutdown_until_scan_finishes(self):
        w = self.window
        w.toggle_scan()
        scanner = w.band_scanner
        event = Mock()
        w.closeEvent(event)
        event.ignore.assert_called_once()
        w.audio.stop_stream.assert_not_called()
        self.assertTrue(w._close_after_scan)
        scanner.active = False
        w._on_band_scan_complete(scanner)
        w.close.assert_called_once()


class DialogBase:
    def __init__(self, parent=None): self.accepted = False
    def accept(self): self.accepted = True


class SettingsWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'config.yaml'
        self.manager = ConfigManager(str(self.path))
        self.manager.save()
        self.messages = Mock()
        cls = controller('cqsentinel/gui/settings_dialog.py', 'SettingsDialog',
                         {'__init__', 'apply_settings', 'accept'},
                         {'get_config_manager': lambda: self.manager, 'deepcopy': copy.deepcopy,
                          'get_radio_info': lambda *args: (3085,), 'QMessageBox': self.messages,
                          'logger': logging.getLogger(__name__)}, base=DialogBase)
        cls.init_ui = lambda self: None
        cls.load_settings = lambda self: None
        self.dialog = cls()
        source = ast.parse((ROOT / 'cqsentinel/gui/settings_dialog.py').read_text(encoding='utf-8-sig'))
        for node in ast.walk(source):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {'currentText', 'currentData', 'text', 'value', 'isChecked'}
                    and isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == 'self'):
                setattr(self.dialog, node.func.value.attr, Control())
        self.dialog.transcription_local_radio.checked = True
        self.dialog.serial_combo.data = 'COM5'
        self.dialog.baud_combo.data = 115200
        self.dialog.sample_rate_combo.data = 16000
        self.dialog.manufacturer_combo.label = 'Icom'
        self.dialog.model_combo.label = 'IC-705'
        self.dialog.noise_reduction_combo.label = 'medium'
        self.dialog.audio_device_combo.label = '(Auto-detect)'
        self.dialog.log_level_combo.label = 'INFO'

    def test_failed_ok_keeps_dialog_open_and_saved_settings_unchanged(self):
        original = self.path.read_bytes()
        with self.assertLogs(level='ERROR'), patch('cqsentinel.config.os.replace', side_effect=OSError('disk failure')):
            self.dialog.accept()
        self.assertFalse(self.dialog.accepted)
        self.assertEqual(self.manager.config.radio.serial_port, '')
        self.assertEqual(self.path.read_bytes(), original)
        self.messages.critical.assert_called_once()

    def test_apply_then_failed_apply_preserves_last_success(self):
        self.assertTrue(self.dialog.apply_settings())
        saved = self.path.read_bytes()
        self.assertTrue(self.dialog.settings_applied)
        self.assertIsNot(self.dialog.config, self.manager.config)
        self.dialog.serial_combo.data = 'COM6'
        with self.assertLogs(level='ERROR'), patch('cqsentinel.config.os.replace', side_effect=OSError('disk failure')):
            self.assertFalse(self.dialog.apply_settings())
        self.assertEqual(self.manager.config.radio.serial_port, 'COM5')
        self.assertEqual(self.path.read_bytes(), saved)

    def test_main_window_observes_applied_changes_even_when_dialog_cancelled(self):
        old_config = copy.deepcopy(self.manager.config)
        self.dialog.apply_settings()
        fake_dialog = SimpleNamespace(settings_applied=True, exec=lambda: 0)
        cls = controller('cqsentinel/gui/main_window.py', 'MainWindow', {'show_settings'},
                         {'SettingsDialog': lambda parent: fake_dialog,
                          'get_config': lambda: self.manager.config,
                          'QMessageBox': self.messages, 'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = old_config
        window.log = Mock()
        window.show_settings()
        self.assertIs(window.config, self.manager.config)
        self.assertEqual(window.config.radio.serial_port, 'COM5')

    def test_backend_change_requires_restart_without_exposing_credentials(self):
        previous = copy.deepcopy(self.manager.config)
        edited = copy.deepcopy(previous)
        edited.audio.openai_api_key = 'synthetic-secret-for-test'
        self.manager.save(edited)
        fake_dialog = SimpleNamespace(settings_applied=True, exec=lambda: 1)
        cls = controller('cqsentinel/gui/main_window.py', 'MainWindow', {'show_settings'},
                         {'SettingsDialog': lambda parent: fake_dialog,
                          'get_config': lambda: self.manager.config,
                          'QMessageBox': self.messages, 'logger': logging.getLogger(__name__)})
        window = cls()
        window.config = previous
        window.log = Mock()
        window.show_settings()
        self.messages.information.assert_called_once()
        message = self.messages.information.call_args.args[-1]
        self.assertIn('Transcription backend settings', message)
        self.assertNotIn(edited.audio.openai_api_key, message)


if __name__ == '__main__':
    unittest.main()
