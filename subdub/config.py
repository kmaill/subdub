"""
Configuration management for subdub.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG_TEMPLATE = """# ==============================================================================
# Subdub Configuration (~/.config/subdub/config.toml)
# ==============================================================================

[tts]
# Microsoft Edge TTS voice model
voice = "pl-PL-MarekNeural"
# Language code for audio track metadata in MKV/MP4 (ISO 639-2: 'pol')
lang = "pol"
# Speech speed modifier (e.g. "+0%", "+5%")
rate = "+0%"
# Speech volume modifier (e.g. "+0%")
volume = "+0%"
# Pitch modifier
pitch = "+0Hz"
# Max parallel requests to edge-tts API
max_concurrency = 4

[audio]
# Sample rate in Hz
sample_rate = 48000
# Window size in seconds for batched mixing (900.0 = 15 minutes)
batch_seconds = 900.0
# Bitrate for 5.1 surround sound (AC3)
bitrate_51 = "448k"
# Bitrate for stereo sound (AC3/AAC)
bitrate_stereo = "256k"
# Audio ducking parameters (compression applied to background music/effects when voice speaks)
ducking_threshold = 0.025
ducking_ratio = 4.0
ducking_attack = 25
ducking_release = 250

[subtitles]
# Strip hearing impaired / sound description tags
strip_sdh = true

[storage]
# Working directory for temporary audio files, cues, and scratchpad.
# If empty, defaults to ~/.cache/subdub on persistent disk.
temp_dir = ""
# Lock file path to prevent concurrent process collisions.
lock_file = ""
# Directories scanned when using 'subdub --scan'
scan_dirs = [
    "/media/movies",
    "/media/tv"
]

[server]
# Webhook server configuration for Bazarr
host = "0.0.0.0"
port = 9999

[jellyfin]
# Notify Jellyfin to refresh media library after voice-over remuxing
enabled = false
url = "http://localhost:8096"
# Token can be set directly or read from environment variable via "env:NAME"
token = "env:JELLYFIN_TOKEN"
"""


@dataclass
class Config:
    # TTS
    voice: str = "pl-PL-MarekNeural"
    lang: str = "pol"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    max_tts_concurrency: int = 4

    # Audio and Mixing
    sample_rate: int = 48000
    batch_seconds: float = 900.0
    bitrate_51: str = "448k"
    bitrate_stereo: str = "256k"
    ducking_threshold: float = 0.025
    ducking_ratio: float = 4.0
    ducking_attack: int = 25
    ducking_release: int = 250

    # Subtitles
    strip_sdh: bool = True

    # Storage and Scanning
    temp_dir: str = ""
    lock_file: str = ""
    scan_dirs: list[str] = field(default_factory=lambda: ["/media/movies", "/media/tv"])

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 9999

    # Jellyfin
    jellyfin_enabled: bool = False
    jellyfin_url: str = "http://localhost:8096"
    jellyfin_token: str = ""

    # Processing flags
    force: bool = False
    dry_run: bool = False

    def __post_init__(self):
        if not self.temp_dir:
            self.temp_dir = str(get_default_cache_dir())
        if not self.lock_file:
            self.lock_file = os.path.join(self.temp_dir, "subdub.lock")

        # Resolve token if referencing environment variable
        if self.jellyfin_token.startswith("env:"):
            env_var = self.jellyfin_token[4:].strip()
            self.jellyfin_token = os.environ.get(env_var, "")
        elif not self.jellyfin_token and "JELLYFIN_TOKEN" in os.environ:
            self.jellyfin_token = os.environ["JELLYFIN_TOKEN"]


def get_default_cache_dir() -> Path:
    """
    Return cache directory.
    """
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "subdub"
    try:
        return Path.home() / ".cache" / "subdub"
    except Exception:
        return Path("/var/tmp") / "subdub"


def get_default_config_path() -> Path:
    """Return configuration path."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = Path(xdg_config)
    else:
        base = Path.home() / ".config"
    return base / "subdub" / "config.toml"


def init_default_config_if_missing(config_path: Path | None = None) -> Path:
    """Create the default configuration file if it does not already exist."""
    path = config_path or get_default_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return path


def load_config(config_path: str | Path | None = None, **cli_overrides: Any) -> Config:
    """
    Load configuration:
    1. Built-in defaults
    2. config.toml file
    3. CLI overrides
    """
    path = Path(config_path) if config_path else get_default_config_path()

    # Automatically generate default config if not present
    if not path.exists():
        try:
            init_default_config_if_missing(path)
        except OSError:
            # If we don't have write permissions to user config, proceed with built-in defaults
            pass

    data: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            # Log warning or re-raise
            sys.stderr.write(f"[WARN] Failed to parse {path}: {e}. Using defaults.\n")

    tts_section = data.get("tts", {})
    audio_section = data.get("audio", {})
    subs_section = data.get("subtitles", {})
    storage_section = data.get("storage", {})
    server_section = data.get("server", {})
    jellyfin_section = data.get("jellyfin", {})

    cfg = Config(
        voice=tts_section.get("voice", Config.voice),
        lang=tts_section.get("lang", Config.lang),
        rate=tts_section.get("rate", Config.rate),
        volume=tts_section.get("volume", Config.volume),
        pitch=tts_section.get("pitch", Config.pitch),
        max_tts_concurrency=tts_section.get("max_concurrency", Config.max_tts_concurrency),
        sample_rate=audio_section.get("sample_rate", Config.sample_rate),
        batch_seconds=float(audio_section.get("batch_seconds", Config.batch_seconds)),
        bitrate_51=audio_section.get("bitrate_51", Config.bitrate_51),
        bitrate_stereo=audio_section.get("bitrate_stereo", Config.bitrate_stereo),
        ducking_threshold=float(audio_section.get("ducking_threshold", Config.ducking_threshold)),
        ducking_ratio=float(audio_section.get("ducking_ratio", Config.ducking_ratio)),
        ducking_attack=int(audio_section.get("ducking_attack", Config.ducking_attack)),
        ducking_release=int(audio_section.get("ducking_release", Config.ducking_release)),
        strip_sdh=subs_section.get("strip_sdh", Config.strip_sdh),
        temp_dir=storage_section.get("temp_dir", ""),
        lock_file=storage_section.get("lock_file", ""),
        scan_dirs=storage_section.get("scan_dirs", ["/media/movies", "/media/tv"]),
        server_host=server_section.get("host", Config.server_host),
        server_port=int(server_section.get("port", Config.server_port)),
        jellyfin_enabled=jellyfin_section.get("enabled", Config.jellyfin_enabled),
        jellyfin_url=jellyfin_section.get("url", Config.jellyfin_url),
        jellyfin_token=jellyfin_section.get("token", Config.jellyfin_token),
    )

    # Apply CLI overrides
    for k, v in cli_overrides.items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)

    return cfg
