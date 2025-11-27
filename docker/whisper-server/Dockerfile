# Custom Whisper Server Dockerfile
# Use this if the fedirz/faster-whisper-server image doesn't work

FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install --no-cache-dir \
    faster-whisper \
    fastapi \
    uvicorn \
    python-multipart

# Create app directory
WORKDIR /app

# Copy server script
COPY whisper_server.py /app/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["python3", "whisper_server.py"]
