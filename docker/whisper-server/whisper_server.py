#!/usr/bin/env python3
"""
Simple Whisper API Server for CQSentinel
OpenAI-compatible API endpoints
"""

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import tempfile
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
MODEL_SIZE = os.getenv('WHISPER_MODEL', 'medium.en')
DEVICE = os.getenv('WHISPER_DEVICE', 'cuda')
COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE_TYPE', 'float16' if DEVICE == 'cuda' else 'float32')
HOST = os.getenv('WHISPER_HOST', '0.0.0.0')
PORT = int(os.getenv('WHISPER_PORT', '8000'))

app = FastAPI(title="Whisper Transcription Server")

# Load model on startup
model = None

@app.on_event("startup")
async def load_model():
    global model
    logger.info(f"Loading Whisper model: {MODEL_SIZE} on {DEVICE}")
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    logger.info("Model loaded successfully")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "model": MODEL_SIZE, "device": DEVICE}

@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form(MODEL_SIZE),
    language: str = Form('en'),
    response_format: str = Form('json')
):
    """OpenAI-compatible transcription endpoint"""
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        # Transcribe
        segments, info = model.transcribe(
            tmp_path,
            language=language,
            beam_size=5,
            vad_filter=True
        )

        # Collect segments
        segment_list = []
        full_text = []

        for segment in segments:
            segment_data = {
                'start': segment.start,
                'end': segment.end,
                'text': segment.text,
                'no_speech_prob': segment.no_speech_prob
            }
            segment_list.append(segment_data)
            full_text.append(segment.text)

        # Clean up temp file
        os.unlink(tmp_path)

        # Return response
        if response_format == 'verbose_json':
            return JSONResponse({
                'text': ' '.join(full_text),
                'segments': segment_list,
                'language': info.language
            })
        else:
            return JSONResponse({
                'text': ' '.join(full_text)
            })

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return JSONResponse(
            status_code=500,
            content={'error': str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
