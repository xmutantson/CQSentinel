"""Real in-process HTTP tests; fake model, no sockets, downloads, or inference.

Run: python -B -m unittest discover -s tests -p test_whisper_http.py -v
Optional dependencies: fastapi, httpx, python-multipart.
"""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MISSING = [name for name in ('fastapi', 'httpx', 'python_multipart')
           if importlib.util.find_spec(name) is None]


@unittest.skipIf(MISSING, 'Optional HTTP test dependencies missing: ' + ', '.join(MISSING))
class WhisperHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.client_class = TestClient
        fake_whisper = types.ModuleType('faster_whisper')
        fake_whisper.WhisperModel = Mock(
            side_effect=AssertionError('An explicitly injected fake model is required'))
        with patch.dict(sys.modules, {'faster_whisper': fake_whisper}):
            spec = importlib.util.spec_from_file_location(
                'http_test_whisper_server', ROOT / 'docker/whisper-server/whisper_server.py')
            cls.server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.server)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = []
        real_temporary = tempfile.NamedTemporaryFile

        def temporary_audio(**kwargs):
            result = real_temporary(dir=self.directory.name, **kwargs)
            self.paths.append(Path(result.name))
            return result

        files = patch.object(self.server.tempfile, 'NamedTemporaryFile',
                             side_effect=temporary_audio)
        files.start()
        self.addCleanup(files.stop)
        self.model = Mock()
        self.model.transcribe.side_effect = self.fake_transcribe
        self.factory = Mock(return_value=self.model)
        model_factory = patch.object(self.server, 'WhisperModel', self.factory)
        model_factory.start()
        self.addCleanup(model_factory.stop)
        self.client = self.client_class(self.server.app)
        self.client.__enter__()  # Startup uses only the fake factory.
        self.addCleanup(self.client.__exit__, None, None, None)

    def fake_transcribe(self, path, **kwargs):
        self.assertEqual(Path(path).read_bytes(), b'synthetic audio')
        return iter([NS(start=0, end=1, text='CQ K1ABC', no_speech_prob=.1)]), NS(language='de')

    def post(self, **kwargs):
        return self.client.post('/v1/audio/transcriptions',
            files={'file': ('test.wav', b'synthetic audio', 'audio/wav')}, **kwargs)

    def assert_cleaned(self):
        self.assertEqual(len(self.paths), 1)
        self.assertFalse(self.paths[0].exists())
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_multipart_fields_and_public_model_alias(self):
        response = self.post(data={'model': 'requested-model', 'language': 'de',
                                   'response_format': 'verbose_json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'text': 'CQ K1ABC', 'language': 'de',
            'segments': [{'start': 0, 'end': 1, 'text': 'CQ K1ABC', 'no_speech_prob': .1}]})
        self.model.transcribe.assert_called_once_with(
            str(self.paths[0]), language='de', beam_size=5, vad_filter=True)
        self.assertIs(self.server.model, self.model)
        schema = self.client.get('/openapi.json').json()
        body = schema['paths']['/v1/audio/transcriptions']['post']['requestBody']
        name = body['content']['multipart/form-data']['schema']['$ref'].rsplit('/', 1)[1]
        properties = schema['components']['schemas'][name]['properties']
        self.assertIn('model', properties)
        self.assertNotIn('requested_model', properties)
        self.assertEqual(properties['model']['default'], self.server.MODEL_SIZE)
        self.assert_cleaned()

    def test_omitted_form_fields_use_defaults(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'text': 'CQ K1ABC'})
        self.model.transcribe.assert_called_once_with(
            str(self.paths[0]), language='en', beam_size=5, vad_filter=True)
        self.assert_cleaned()

    def test_missing_upload_is_rejected_before_handler(self):
        response = self.client.post('/v1/audio/transcriptions', data={'model': 'medium.en'})
        self.assertEqual(response.status_code, 422)
        self.assertIn(['body', 'file'], [item['loc'] for item in response.json()['detail']])
        self.model.transcribe.assert_not_called()
        self.assertEqual(self.paths, [])

    def test_model_failure_cleans_temporary_audio(self):
        self.model.transcribe.side_effect = RuntimeError('synthetic model failure')
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'error': 'synthetic model failure'})
        self.assert_cleaned()

    def test_lazy_segment_failure_cleans_temporary_audio(self):
        def segments():
            yield NS(start=0, end=1, text='partial', no_speech_prob=.1)
            raise RuntimeError('synthetic segment failure')
        self.model.transcribe.side_effect = None
        self.model.transcribe.return_value = segments(), NS(language='en')
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'error': 'synthetic segment failure'})
        self.assert_cleaned()

    def test_upload_read_failure_cleans_temporary_audio(self):
        with patch('starlette.datastructures.UploadFile.read',
                   new=AsyncMock(side_effect=OSError('synthetic upload failure'))):
            response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'error': 'synthetic upload failure'})
        self.model.transcribe.assert_not_called()
        self.assert_cleaned()

    def test_startup_and_health_use_configured_model(self):
        self.factory.assert_called_once_with(self.server.MODEL_SIZE,
            device=self.server.DEVICE, compute_type=self.server.COMPUTE_TYPE)
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'model': self.server.MODEL_SIZE,
                                          'device': self.server.DEVICE})
        self.model.transcribe.assert_not_called()
        self.assertEqual(self.paths, [])


if __name__ == '__main__':
    unittest.main()
