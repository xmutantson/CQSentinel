# Network Transcription Feature

CQSentinel now supports **3 transcription methods** for speech-to-text:

1. **Local Processing** (default) - Uses GPU/CPU on the CQSentinel machine
2. **Network Server** - Offloads to remote Whisper server
3. **OpenAI API** - Cloud-based transcription

## Choosing a Method

### Via Settings UI (Recommended)

1. Open CQSentinel
2. Go to **File → Settings** (or press Settings button)
3. Click the **Audio** tab
4. Under **Speech Transcription Method**, select your preferred option:
   - **Local Processing (GPU/CPU)** - Default, free, uses your machine's resources
   - **Network Server** - Offload to remote server (see setup below)
   - **OpenAI API** - Cloud transcription (~$0.006/minute)

### Via Configuration File

Edit `~/.cqsentinel/config.yaml`:

```yaml
audio:
  # Option 1: Local processing (default)
  network_whisper_enabled: false
  openai_api_key: ""

  # Option 2: Network server
  network_whisper_enabled: true
  network_whisper_url: "http://192.168.1.100:8000"
  network_whisper_model: "medium.en"
  network_whisper_timeout: 30.0

  # Option 3: OpenAI API
  openai_api_key: "sk-your-key-here"
  openai_whisper_model: "whisper-1"
```

## Network Server Setup

### Quick Start (Docker)

On your Linux server with GPU:

```bash
# Clone CQSentinel repo
git clone https://github.com/xmutantson/CQSentinel.git
cd CQSentinel

# Start Whisper server
docker-compose -f docker-compose.whisper.yml up -d

# Verify it's running
curl http://localhost:8000/health
```

### Configure CQSentinel

In CQSentinel Settings UI:

1. Select **Network Server** radio button
2. Enter **Server URL**: `http://YOUR_SERVER_IP:8000`
3. Select **Model**: `medium.en` (recommended)
4. Set **Timeout**: `30.0` seconds
5. Click **Apply** and **OK**

Or edit config.yaml:

```yaml
audio:
  network_whisper_enabled: true
  network_whisper_url: "http://192.168.1.100:8000"
  network_whisper_model: "medium.en"
  network_whisper_timeout: 30.0
```

## Priority Order

CQSentinel uses this priority when multiple options are configured:

1. **Network Server** (if `network_whisper_enabled: true`)
2. **OpenAI API** (if API key provided)
3. **Local Processing** (fallback)

## Comparison

| Method | Cost | Performance | Requirements |
|--------|------|-------------|--------------|
| **Local** | Free | GPU: Fast<br>CPU: Slow | GPU recommended (4+ GB VRAM) |
| **Network** | Free | Fast | Linux server with GPU |
| **OpenAI API** | $0.006/min | Fast | Internet, API key |

## Benefits of Network Transcription

✅ **Offload processing** - Run CQSentinel on laptop, Whisper on desktop/server
✅ **Share resources** - Multiple CQSentinel instances → one server
✅ **Better hardware** - Use server's powerful GPU
✅ **Self-hosted** - Full data privacy, no cloud costs

## Troubleshooting

### "Cannot connect to Whisper server"

1. Verify server is running: `docker ps`
2. Check firewall: `sudo ufw allow 8000/tcp`
3. Test connection: `curl http://SERVER_IP:8000/health`
4. Check server logs: `docker logs cqsentinel-whisper`

### Transcription slow/timing out

1. Increase timeout in settings (try 60 seconds)
2. Check network latency: `ping SERVER_IP`
3. Verify server isn't overloaded: `docker stats cqsentinel-whisper`

### Want to use CPU instead of GPU

Edit `docker-compose.whisper.yml` and uncomment the `whisper-server-cpu` service:

```bash
docker-compose -f docker-compose.whisper.yml up whisper-server-cpu -d
```

## Files

- **[docker-compose.whisper.yml](../docker-compose.whisper.yml)** - Docker Compose for Whisper server
- **[WHISPER_SERVER_SETUP.md](WHISPER_SERVER_SETUP.md)** - Detailed server setup guide
- **[cqsentinel/speech/network_transcriber.py](../cqsentinel/speech/network_transcriber.py)** - Network transcriber implementation
- **[cqsentinel/config.py](../cqsentinel/config.py)** - Configuration dataclasses

## See Also

- [Whisper Server Setup Guide](WHISPER_SERVER_SETUP.md) - Complete server installation instructions
- [faster-whisper-server](https://github.com/fedirz/faster-whisper-server) - Server software
- [OpenAI Whisper](https://github.com/openai/whisper) - Whisper model information
