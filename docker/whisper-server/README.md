# CQSentinel Whisper Server (Docker)

Self-hosted Whisper transcription server for CQSentinel using Docker.

## Quick Start

### GPU Version (Recommended)

```bash
# From CQSentinel root directory
docker-compose -f docker-compose.whisper.yml up -d

# Or from this directory
docker-compose up -d
```

### CPU Version

Edit `docker-compose.whisper.yml` and uncomment the `whisper-server-cpu` service.

## Configuration

The server is configured via environment variables in `docker-compose.yml`:

```yaml
environment:
  - WHISPER_MODEL=medium.en      # Model: tiny, base, small, medium, large
  - WHISPER_DEVICE=cuda          # Device: cuda or cpu
  - WHISPER_COMPUTE_TYPE=float16 # float16 (GPU) or float32 (CPU)
  - WHISPER_HOST=0.0.0.0
  - WHISPER_PORT=8000
  - WHISPER_BEAM_SIZE=5          # Beam search size (higher = more accurate)
```

## Verify Server

```bash
# Health check
curl http://localhost:8000/health

# Should return: {"status":"ok","model":"medium.en","device":"cuda"}
```

## Connect from CQSentinel

Edit `~/.cqsentinel/config.yaml`:

```yaml
audio:
  network_whisper_enabled: true
  network_whisper_url: "http://YOUR_SERVER_IP:8000"
  network_whisper_model: "medium.en"
```

## Logs

```bash
# View logs
docker-compose -f docker-compose.whisper.yml logs -f

# Or
docker logs -f cqsentinel-whisper
```

## Stop Server

```bash
docker-compose -f docker-compose.whisper.yml down
```

## Troubleshooting

### GPU not detected

Ensure NVIDIA Container Toolkit is installed:

```bash
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Model download slow

The first startup will download the Whisper model (~1.5 GB for medium.en). Check logs:

```bash
docker-compose logs -f
```

### Container won't start

Check Docker GPU support:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```
