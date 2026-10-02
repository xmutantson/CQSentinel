"""Offline endpoint body/backend contract tests; no HTTP/model runtime is started."""
import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np

from cqsentinel.speech.openai_transcriber import OpenAITranscriber, OpenAITranscriptionResult
from cqsentinel.speech.router import TranscriptionRouter

ROOT = Path(__file__).resolve().parents[1]


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


class FakeApp:
    def __init__(self, **kwargs):
        pass

    def on_event(self, *args, **kwargs):
        return lambda function: function

    get = post = on_event


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class Upload:
    def __init__(self, fail=False):
        self.fail = fail

    async def read(self):
        if self.fail:
            raise OSError('upload failed')
        return b'synthetic audio; model is stubbed'


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Stub only optional framework/model boundaries. The handler body is real.
        fake_modules = {
            'fastapi': module('fastapi', FastAPI=FakeApp, UploadFile=Upload,
                              File=lambda *args, **kwargs: None,
                              Form=lambda default, **kwargs: default),
            'fastapi.responses': module('fastapi.responses', JSONResponse=FakeResponse),
            'faster_whisper': module('faster_whisper', WhisperModel=Mock()),
        }
        with patch.dict(sys.modules, fake_modules):
            spec = importlib.util.spec_from_file_location('offline_whisper_server',
                ROOT / 'docker/whisper-server/whisper_server.py')
            cls.server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.server)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        real_temporary = tempfile.NamedTemporaryFile
        files = patch.object(self.server.tempfile, 'NamedTemporaryFile',
            side_effect=lambda **kwargs: real_temporary(dir=self.directory.name, **kwargs))
        files.start()
        self.addCleanup(files.stop)
        self.model = Mock()
        self.model.transcribe.return_value = (
            iter([NS(start=0, end=1, text='CQ K1ABC', no_speech_prob=.1)]),
            NS(language='en'))
        self.server.model = self.model

    def assert_no_temporary_files(self):
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_request_model_name_does_not_shadow_loaded_model(self):
        response = asyncio.run(self.server.transcribe_audio(
            Upload(), requested_model='medium.en', response_format='verbose_json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content['text'], 'CQ K1ABC')
        self.assertEqual(response.content['segments'][0]['no_speech_prob'], .1)
        self.model.transcribe.assert_called_once()
        self.assert_no_temporary_files()

    def test_inference_failure_cleans_temporary_audio(self):
        self.model.transcribe.side_effect = RuntimeError('inference failed')
        response = asyncio.run(self.server.transcribe_audio(Upload()))
        self.assertEqual(response.status_code, 500)
        self.assert_no_temporary_files()

    def test_upload_read_failure_cleans_temporary_audio(self):
        response = asyncio.run(self.server.transcribe_audio(Upload(fail=True)))
        self.assertEqual(response.status_code, 500)
        self.model.transcribe.assert_not_called()
        self.assert_no_temporary_files()

    def test_segment_iteration_failure_cleans_temporary_audio(self):
        def failing_segments():
            raise RuntimeError('lazy inference failed')
            yield
        self.model.transcribe.return_value = failing_segments(), NS(language='en')
        response = asyncio.run(self.server.transcribe_audio(Upload()))
        self.assertEqual(response.status_code, 500)
        self.assert_no_temporary_files()


class BackendTests(unittest.TestCase):
    def test_capture_stop_race_interrupts_newly_opened_recording(self):
        cancelled = [False]
        def start_recording(*args, **kwargs):
            cancelled[0] = True  # Stop arrives while the device is being opened.
            return np.ones(160, dtype=np.float32)
        sounddevice = module('sounddevice', InputStream=object,
            rec=Mock(side_effect=start_recording), get_stream=lambda: NS(active=True),
            stop=Mock(), wait=Mock())
        with patch.dict(sys.modules, {'sounddevice': sounddevice}):
            spec = importlib.util.spec_from_file_location('offline_capture', ROOT / 'cqsentinel/audio/capture.py')
            capture_module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'offline_capture': capture_module}):
                spec.loader.exec_module(capture_module)
                audio = capture_module.AudioCapture()
                result = audio.record(60, cancel_requested=lambda: cancelled[0])
                self.assertEqual(len(result), 0)
                sounddevice.stop.assert_called_once()
                sounddevice.wait.assert_not_called()
                audio.record(60, cancel_requested=lambda: True)
                sounddevice.rec.assert_called_once()

    def test_cloud_backend_accepts_frequency_and_preserves_request_identity(self):
        backend = OpenAITranscriber(api_key='synthetic-test-key')
        backend.transcribe = Mock(return_value=OpenAITranscriptionResult(text='CQ K1ABC', success=True))
        router = TranscriptionRouter(backend)
        request_id = router.transcribe_async(audio=np.zeros(160), sample_rate=16000, frequency_hz=14150000)
        for thread in backend._active_threads:
            thread.join(1)
        result = router.get_result_for(request_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.frequency_hz, 14150000)
        self.assertEqual(result.request_id, request_id)

    def test_preprocessing_pipeline_does_not_construct_local_model(self):
        local_model = Mock(side_effect=AssertionError('local model must remain disabled'))
        denoiser = NS(set_strength=lambda value: None, denoise=lambda audio: audio)
        vad = NS(detect_speech=lambda audio: [], get_speech_ratio=lambda audio: 1.0)
        fake_modules = {
            'cqsentinel.audio.denoiser': module('cqsentinel.audio.denoiser', AudioDenoiser=lambda **kwargs: denoiser),
            'cqsentinel.audio.vad': module('cqsentinel.audio.vad', VoiceActivityDetector=lambda **kwargs: vad),
            'cqsentinel.speech.transcription': module('cqsentinel.speech.transcription', SpeechTranscriber=local_model, TranscriptSegment=object),
            'cqsentinel.voice.embeddings': module('cqsentinel.voice.embeddings', VoiceEmbedder=Mock(), VoiceSegment=object),
        }
        with patch.dict(sys.modules, fake_modules):
            spec = importlib.util.spec_from_file_location('offline_pipeline', ROOT / 'cqsentinel/audio/pipeline.py')
            pipeline_module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'offline_pipeline': pipeline_module}):
                spec.loader.exec_module(pipeline_module)
                pipeline = pipeline_module.AudioPipeline(enable_voice_id=False, enable_transcription=False)
                result = pipeline.process(np.ones(160), transcribe=False)
        local_model.assert_not_called()
        self.assertTrue(result.has_speech)
        self.assertEqual(result.transcripts, [])


if __name__ == '__main__':
    unittest.main()
