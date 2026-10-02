"""Offline persistence and transcription ownership regressions."""
import copy
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cqsentinel.config import ConfigManager
from cqsentinel.speech.router import TranscriptionRouter


class FakeBackend:
    def __init__(self):
        self.results = queue.Queue()
        self.requests = []

    def transcribe_async(self, **kwargs):
        self.requests.append(kwargs)
        return len(self.requests)

    def get_result(self, timeout=0):
        try:
            return self.results.get_nowait()
        except queue.Empty:
            return None


class RouterTests(unittest.TestCase):
    def test_out_of_order_results_remain_owned_by_request(self):
        backend = FakeBackend()
        router = TranscriptionRouter(backend)
        first = router.transcribe_async(audio=[], frequency_hz=14150000)
        second = router.transcribe_async(audio=[], frequency_hz=7200000)
        backend.results.put(SimpleNamespace(request_id=second, text='second'))
        backend.results.put(SimpleNamespace(request_id=first, text='first'))
        self.assertEqual(router.get_result_for(first).text, 'first')
        self.assertEqual(router.get_result_for(second).text, 'second')
        self.assertIsNone(router.get_result_for(first))

    def test_cancelled_late_result_cannot_satisfy_new_request(self):
        backend = FakeBackend()
        router = TranscriptionRouter(backend)
        old = router.transcribe_async(audio=[])
        router.cancel(old)
        current = router.transcribe_async(audio=[])
        backend.results.put(SimpleNamespace(request_id=old, text='stale'))
        self.assertIsNone(router.get_result_for(current))
        self.assertIsNone(router.get_result_for(old))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'settings.yaml'
        self.manager = ConfigManager(str(self.path))

    def test_failed_replace_preserves_file_and_active_configuration(self):
        self.manager.save()
        original = self.path.read_bytes()
        edited = copy.deepcopy(self.manager.config)
        edited.radio.serial_port = 'COM99'
        with patch('cqsentinel.config.os.replace', side_effect=OSError('disk failure')):
            with self.assertLogs('cqsentinel.config', level='ERROR'), self.assertRaises(OSError):
                self.manager.save(edited)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.manager.config.radio.serial_port, '')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_successful_save_publishes_candidate_and_round_trips_unicode(self):
        edited = copy.deepcopy(self.manager.config)
        edited.radio.audio_device_name = 'Récepteur USB'
        self.manager.save(edited)
        self.assertIs(self.manager.config, edited)
        loaded = ConfigManager(str(self.path)).load()
        self.assertEqual(loaded.radio.audio_device_name, edited.radio.audio_device_name)

    def test_future_fields_survive_load_and_save(self):
        self.path.write_text('future: keep\nradio:\n  future_radio: 7\n  serial_port: COM5\n', encoding='utf-8')
        self.manager.load()
        self.assertEqual(self.manager.config.radio.serial_port, 'COM5')
        self.manager.save()
        text = self.path.read_text(encoding='utf-8')
        self.assertIn('future: keep', text)
        self.assertIn('future_radio: 7', text)

    def test_malformed_or_nonmapping_config_is_never_overwritten(self):
        for malformed in ('[unterminated', 'false', '0', '[]', 'radio: []'):
            with self.subTest(malformed=malformed):
                self.path.write_text(malformed, encoding='utf-8')
                manager = ConfigManager(str(self.path))
                with self.assertLogs('cqsentinel.config', level='ERROR'), self.assertRaises(Exception):
                    manager.load()
                with self.assertRaises(ValueError):
                    manager.save()
                self.assertEqual(self.path.read_text(encoding='utf-8'), malformed)


if __name__ == '__main__':
    unittest.main()
