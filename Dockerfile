FROM python:3.12-slim-bookworm

LABEL maintainer="Kamil"
LABEL description="AI voice-over (TTS) generator and remuxer for video media"

# Install system dependencies (FFmpeg and MKVToolNix)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mkvtoolnix \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project definition and source code
COPY pyproject.toml README.md ./
COPY subdub/ ./subdub/

# Install Python package and edge-tts
RUN pip install --no-cache-dir .

# Create cache and config directories on persistent filesystem
RUN mkdir -p /root/.config/subdub /root/.cache/subdub

# Expose Webhook server port for Bazarr
EXPOSE 9999

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9999/health || exit 1

ENTRYPOINT ["subdub"]
CMD ["--serve", "--host", "0.0.0.0", "--port", "9999"]
