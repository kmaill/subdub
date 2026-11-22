# subdub

[![CI/CD](https://github.com/kmaill/subdub/actions/workflows/ci.yml/badge.svg)](https://github.com/kmaill/subdub/actions/workflows/ci.yml)

**English** | [Wersja polska](README_PL.md)

> **Lightweight CLI tool and Python microservice that automatically generates and embeds AI voice-over audio tracks into video files (`.mkv`, `.mp4`, `.m4v`, `.mov`).**

Designed for low resource usage and seamless automation within the **Bazarr / Jellyfin** home media stack. Powered by free Microsoft Edge TTS synthesis, supporting any language available in Edge TTS (such as Polish, Spanish, German, Ukrainian, French, English, and more), with examples configured for Polish voice-over (`pl-PL-MarekNeural`).

---

## Features

* **Free AI Voice-Over:** Uses Microsoft Edge TTS models. Supports dozens of languages and voices out of the box (e.g. Spanish, German, Ukrainian, English, French).
* **Minimal RAM Usage:** Audio is mixed in 15-minute time windows. Boundary carryover eliminates clipped words across batches while keeping very low memory usage even for 3-hour 4K movies.
* **Smart Audio Ducking:** Automatically compresses and lowers the original soundtrack volume whenever the narrator speaks.
* **Dual Operation Mode:**
  1. CLI tool for single video processing or automated library scans.
  2. Zero-dependency webhook server receiving notifications directly from Bazarr.

---

## How It Works

```text
 +--------------------+       +---------------------+
 |  Bazarr (Webhook)  |   OR  |  CLI (Manual/Scan)  |
 +---------+----------+       +----------+----------+
           |                             |
           +-----------> [ FIFO Queue ] <+
                                |
                      [ Background Worker ]
                                |
          1. Subtitle detection/extraction (SRT) and SDH cleaning
          2. Parallel TTS synthesis (Edge TTS)
          3. 15-minute batched audio mixing with ducking
          4. Safe remux to temporary file and replacement
                                |
                                v
                    +-----------------------+
                    | Jellyfin Notification |
                    +-----------------------+
```

---

## Quick Start (Docker Compose)

The easiest way to run `subdub` alongside Bazarr and Jellyfin:

```yaml
services:
  subdub:
    image: ghcr.io/kmaill/subdub:latest
    container_name: subdub
    restart: unless-stopped
    ports:
      - "9999:9999"
    environment:
      - JELLYFIN_TOKEN=your_jellyfin_api_token
    volumes:
      - ./config:/root/.config/subdub
      - ./cache:/root/.cache/subdub
      # Important: Media paths must match Bazarr container paths 1:1
      - /path/to/movies:/path/to/movies
      - /path/to/tv:/path/to/tv
    deploy:
      resources:
        limits:
          memory: 1200M
```

Start the container:
```bash
docker compose up -d
```

---

## Bazarr Integration

To let Bazarr automatically trigger voice-over generation upon subtitle download:

1. In Bazarr, navigate to: **Settings $\to$ Notifications**.
2. Click the plus icon **(+)** and select provider type: **JSON**.
3. In the **URL** field, paste:
   ```text
   json://subdub:9999/webhook?:path={bazarr_movie_path}{bazarr_episode_path}&:subtitles={bazarr_movie_subtitles}{bazarr_episode_subtitles}
   ```
4. Save the notification.

When Bazarr downloads subtitles:
1. Bazarr sends a notification to `subdub`.
2. `subdub` immediately enqueues the job into its FIFO queue.
3. The background worker synthesizes speech, mixes audio, and replaces the file atomically.
4. Jellyfin receives an API refresh notification.

---

## Command Line Usage (CLI)

### Local Installation (Python 3.11+)

```bash
git clone https://github.com/kmaill/subdub.git
cd subdub
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

System requirements: `ffmpeg` and optionally `mkvtoolnix` (`mkvmerge`).

### Examples

```bash
# Process a single video (automatically finds external or embedded subtitles)
subdub "/path/to/movie.mkv"

# Process a video with explicit subtitle file
subdub "/path/to/movie.mkv" --subs "/path/to/subtitles.srt"

# Force voice-over generation even if target language audio already exists
subdub "/path/to/movie.mkv" --force

# Scan library directory (processes 1 missing file and exits, ideal for cron)
subdub --scan "/media/movies"

# Scan entire library and process all missing videos sequentially
subdub --scan "/media/movies" --all

# Launch the webhook server on port 9999
subdub --serve --port 9999
```

---

## Configuration (`~/.config/subdub/config.toml`)

On first run, the configuration file is created automatically at `~/.config/subdub/config.toml`:

```toml
[tts]
# Voice model (e.g. pl-PL-MarekNeural, es-ES-AlvaroNeural, de-DE-ConradNeural, en-US-GuyNeural)
voice = "pl-PL-MarekNeural"
# ISO 639-2 language code for audio metadata in MKV/MP4 (e.g. pol, spa, deu, eng)
lang = "pol"
rate = "+0%"
volume = "+0%"
max_concurrency = 4

[audio]
sample_rate = 48000
batch_seconds = 900.0
bitrate_51 = "448k"
bitrate_stereo = "256k"
ducking_threshold = 0.025
ducking_ratio = 4.0

[subtitles]
strip_sdh = true

[storage]
temp_dir = ""
scan_dirs = ["/media/movies", "/media/tv"]

[server]
host = "0.0.0.0"
port = 9999

[jellyfin]
enabled = false
url = "http://localhost:8096"
token = "env:JELLYFIN_TOKEN"
```

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. See [LICENSE](LICENSE) for details.
