# Whisper Server Setup Guide

This guide explains how to set up a self-hosted Whisper transcription server that CQSentinel can connect to over the network. This allows you to offload transcription to a more powerful machine (e.g., one with a better GPU) while running CQSentinel on a laptop or lower-powered machine.

## Why Use a Network Whisper Server?

- **Offload processing**: Run Whisper on a powerful GPU server while CQSentinel runs on a laptop
- **Share resources**: Multiple CQSentinel instances can share one Whisper server
- **Reduce local resource usage**: No need for GPU or large RAM on the CQSentinel machine
- **Self-hosted**: Unlike OpenAI API, you control your data and have no usage costs

## Quick Start (Docker - Recommended)

**Easiest option**: Just run Docker Compose!

### GPU Version (Recommended)

```bash
# On your Linux server with NVIDIA GPU
cd /path/to/CQSentinel
docker-compose -f docker-compose.whisper.yml up -d

# Verify it's running
curl http://localhost:8000/health
```

### CPU Version

Edit `docker-compose.whisper.yml` and uncomment the `whisper-server-cpu` service, then:

```bash
docker-compose -f docker-compose.whisper.yml up whisper-server-cpu -d
```

That's it! The server is now running on port 8000 with the medium.en model.

## Architecture

```
┌─────────────────┐                    ┌──────────────────────┐
│   CQSentinel    │   HTTP/REST API    │  Whisper Server      │
│   (Windows/     ├───────────────────>│  (Linux/GPU)         │
│    Linux)       │   Audio WAV files  │                      │
│                 │<───────────────────│  faster-whisper      │
└─────────────────┘   Transcribed text └──────────────────────┘
```

## Server Requirements

### Minimum Recommended:
- **CPU**: 4+ cores (for CPU inference)
- **RAM**: 8 GB
- **Disk**: 2 GB for model files

### GPU-Accelerated (Recommended):
- **GPU**: NVIDIA GPU with 4+ GB VRAM (8 GB+ for medium model)
- **CUDA**: CUDA 11.x or 12.x
- **RAM**: 4 GB
- **Disk**: 2 GB for model files

## Installation Options

### Option 1: Docker (Easiest - Recommended)

**Prerequisites**: Docker and Docker Compose installed, NVIDIA Container Toolkit for GPU support.

#### Install Docker (if not already installed)

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

#### Install NVIDIA Container Toolkit (for GPU support)

```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

#### Run Whisper Server

```bash
# Clone CQSentinel repository (if you haven't already)
git clone https://github.com/xmutantson/CQSentinel.git
cd CQSentinel

# Start the Whisper server
docker-compose -f docker-compose.whisper.yml up -d

# Check logs
docker-compose -f docker-compose.whisper.yml logs -f

# Test the server
curl http://localhost:8000/health
```

**Configuration**: Edit `docker-compose.whisper.yml` to change model, device, or port.

**To stop the server**:
```bash
docker-compose -f docker-compose.whisper.yml down
```

### Option 2: faster-whisper-server (GitHub Install)

**faster-whisper-server** is a production-ready Whisper API server with OpenAI-compatible endpoints.

#### Installation from GitHub

Since the package isn't on PyPI, install directly from GitHub:

```bash
# Create project directory
mkdir -p ~/whisper-server
cd ~/whisper-server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install from GitHub
pip install git+https://github.com/fedirz/faster-whisper-server.git

# OR clone and install manually
git clone https://github.com/fedirz/faster-whisper-server.git
cd faster-whisper-server
pip install -e .
```

#### GPU Support (NVIDIA CUDA)

For GPU acceleration, install CUDA first:

```bash
# Ubuntu/Debian - NVIDIA CUDA
# See: https://developer.nvidia.com/cuda-downloads

# Example for Ubuntu 22.04:
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install cuda-toolkit-12-3

# Verify CUDA
nvidia-smi
```

#### Run the Server

```bash
# Activate virtual environment
source ~/whisper-server/venv/bin/activate

# Start server with medium.en model on GPU
uvicorn faster_whisper_server.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --env WHISPER_MODEL=medium.en \
  --env WHISPER_DEVICE=cuda

# OR for CPU:
uvicorn faster_whisper_server.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --env WHISPER_MODEL=medium.en \
  --env WHISPER_DEVICE=cpu
```

### Option 3: whisper-asr-webservice

**whisper-asr-webservice** is available via pip and works out of the box.

#### Installation

```bash
# Create project directory
mkdir -p ~/whisper-server
cd ~/whisper-server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install whisper-asr-webservice
pip install -U openai-whisper
pip install flask

# Clone the webservice
git clone https://github.com/ahmetoner/whisper-asr-webservice.git
cd whisper-asr-webservice

# Install dependencies
pip install -r requirements.txt
```

#### Run the Server

```bash
# GPU version
gunicorn --bind 0.0.0.0:8000 --workers 1 --timeout 300 app:app

# CPU version
ASR_MODEL=medium.en \
ASR_ENGINE=openai_whisper \
gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 300 app:app
```

### Option 4: Simple FastAPI Server (Custom)

Create your own lightweight server:

#### 1. Install Dependencies

```bash
mkdir -p ~/whisper-server
cd ~/whisper-server
python3 -m venv venv
source venv/bin/activate

pip install faster-whisper fastapi uvicorn python-multipart
```

#### 2. Create `whisper_server.py`

```python
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

# Configuration
MODEL_SIZE = os.getenv('WHISPER_MODEL', 'medium.en')
DEVICE = os.getenv('WHISPER_DEVICE', 'cuda')
COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE_TYPE', 'float16' if DEVICE == 'cuda' else 'float32')

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
    return {"status": "ok"}

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
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### 3. Run the Server

```bash
# Make executable
chmod +x whisper_server.py

# Run with GPU
WHISPER_MODEL=medium.en WHISPER_DEVICE=cuda python whisper_server.py

# OR with CPU
WHISPER_MODEL=medium.en WHISPER_DEVICE=cpu python whisper_server.py
```

#### 4. Test the Server

```bash
# Health check
curl http://localhost:8000/health

# Test transcription
ffmpeg -f lavfi -i "sine=frequency=1000:duration=1" test.wav
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F "file=@test.wav" \
  -F "model=medium.en"
```

## Running as a Service (systemd)

Create `/etc/systemd/system/whisper-server.service`:

```ini
[Unit]
Description=Whisper Transcription Server
After=network.target

[Service]
Type=simple
User=whisper
WorkingDirectory=/home/whisper/whisper-server
Environment="PATH=/home/whisper/whisper-server/venv/bin"
ExecStart=/home/whisper/whisper-server/venv/bin/faster-whisper-server --config /home/whisper/whisper-server/config.yaml
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable whisper-server
sudo systemctl start whisper-server
sudo systemctl status whisper-server
```

## Firewall Configuration

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 8000/tcp

# firewalld (RHEL/Rocky/Fedora)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

## CQSentinel Configuration

### 1. Enable Network Transcription

Edit your CQSentinel config file (`~/.cqsentinel/config.yaml`):

```yaml
audio:
  # ... other audio settings ...

  # Network Whisper Server (self-hosted, supersedes local when enabled)
  network_whisper_enabled: true
  network_whisper_url: "http://192.168.1.100:8000"  # Your server IP
  network_whisper_model: "medium.en"
  network_whisper_timeout: 30.0

  # Disable local transcription (optional - will auto-fallback if network fails)
  # use_gpu: false
```

### 2. Test Connection

Start CQSentinel and check the initialization log:

```
Initializing Network Whisper server connection...
Network Whisper server ready (http://192.168.1.100:8000, model=medium.en)
[INFO] Using network transcription - local GPU/CPU not used
```

If connection fails, you'll see:

```
WARNING: Cannot connect to Whisper server at http://192.168.1.100:8000
Falling back to OpenAI API or local transcription...
```

## Performance Tuning

### GPU Memory

For medium.en model:
- **Required VRAM**: ~2-3 GB
- **Optimal VRAM**: 4+ GB

Check GPU usage:

```bash
watch -n 1 nvidia-smi
```

### CPU Performance

For CPU-only servers, increase workers for better throughput:

```yaml
server:
  workers: 4  # Use number of CPU cores
```

### Network Latency

- **LAN**: < 1s overhead (negligible)
- **WiFi**: 1-2s overhead
- **WAN**: Depends on bandwidth and latency

## Troubleshooting

### Server won't start

```bash
# Check if port is already in use
sudo netstat -tlnp | grep 8000

# Check logs
journalctl -u whisper-server -f
```

### CUDA out of memory

Reduce batch size or use smaller model:

```yaml
whisper:
  model: small.en  # Instead of medium.en
```

### Connection timeout from CQSentinel

Increase timeout in CQSentinel config:

```yaml
audio:
  network_whisper_timeout: 60.0  # Increase to 60 seconds
```

### Model downloads fail

Pre-download models manually:

```bash
source ~/whisper-server/venv/bin/activate
python -c "from faster_whisper import WhisperModel; WhisperModel('medium.en', download_root='/home/whisper/.cache/whisper')"
```

## Security Considerations

### Network Exposure

The Whisper server accepts audio files and returns transcriptions. Consider:

1. **Firewall**: Only allow connections from trusted IPs
   ```bash
   sudo ufw allow from 192.168.1.0/24 to any port 8000
   ```

2. **Reverse Proxy**: Use nginx with authentication:
   ```nginx
   location /v1/audio/transcriptions {
       auth_basic "Whisper Server";
       auth_basic_user_file /etc/nginx/.htpasswd;
       proxy_pass http://localhost:8000;
   }
   ```

3. **VPN**: Run server on VPN network (Tailscale, WireGuard)

## Model Comparison

| Model      | VRAM | Speed     | Accuracy | Best For              |
|------------|------|-----------|----------|-----------------------|
| tiny.en    | 1 GB | Very Fast | Low      | Testing only          |
| base.en    | 1 GB | Fast      | Medium   | Quick transcription   |
| small.en   | 2 GB | Medium    | Good     | Resource-constrained  |
| **medium.en** | **3 GB** | **Medium**   | **Excellent** | **Recommended (SSB)** |
| large-v3   | 5 GB | Slow      | Best     | Critical accuracy     |

**Recommendation**: Use `medium.en` for ham radio SSB audio - best balance of accuracy and speed.

## Advanced: Multiple CQSentinel Instances

One Whisper server can handle multiple CQSentinel clients:

```
CQSentinel (192.168.1.10)  ─┐
                             │
CQSentinel (192.168.1.11)  ─┼──> Whisper Server (192.168.1.100:8000)
                             │
CQSentinel (192.168.1.12)  ─┘
```

All clients use the same config:

```yaml
audio:
  network_whisper_enabled: true
  network_whisper_url: "http://192.168.1.100:8000"
```

## Resources

- **faster-whisper-server**: https://github.com/fedirz/faster-whisper-server
- **faster-whisper**: https://github.com/SYSTRAN/faster-whisper
- **OpenAI Whisper**: https://github.com/openai/whisper
- **CUDA Installation**: https://developer.nvidia.com/cuda-downloads

## Summary

Network transcription setup:

1. **Install faster-whisper-server** on Linux GPU server
2. **Start server** on port 8000
3. **Configure CQSentinel** to use `network_whisper_enabled: true`
4. **Test connection** and verify transcriptions work

Benefits:
- Offload processing from CQSentinel machine
- Better performance with dedicated GPU
- Share server across multiple radios/instances
- Self-hosted (no cloud costs or data privacy concerns)
