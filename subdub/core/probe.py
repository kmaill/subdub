"""
Detects existing audio/subtitle tracks, duration, and channel layouts.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from subdub.core.languages import resolve_language, LanguageSpec

logger = logging.getLogger("subdub.probe")

SAFE_SUBTITLE_CODECS = (
    "subrip",
    "srt",
    "ass",
    "ssa",
    "mov_text",
    "webvtt",
)

MP4_EXTENSIONS = (".mp4", ".m4v", ".mov")
SUPPORTED_VIDEO_EXTENSIONS = (".mkv", *MP4_EXTENSIONS)


@dataclass
class AudioLayout:
    layout: str  # "5.1" or "stereo"
    channels: int  # 6 or 2
    bitrate: str  # e.g. "448k" or "256k"
    title_suffix: str  # "5.1" or "Stereo"


@dataclass
class MediaInfo:
    path: str
    duration: float
    streams: list[dict[str, Any]]
    audio_streams: list[dict[str, Any]]
    subtitle_streams: list[dict[str, Any]]
    has_target_audio: bool
    audio_layout: AudioLayout
    safe_sub_indices: list[int]


def get_video_duration(video_path: str | Path) -> float:
    """Reads media duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError(f"Failed to read media duration: {res.stderr.strip()}")
    try:
        return float(res.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"Invalid duration format: '{res.stdout.strip()}'") from e


def probe_streams(video_path: str | Path) -> list[dict[str, Any]]:
    """Inspects all streams in media file."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"ffprobe failed for {video_path}: {res.stderr}")
        return []
    try:
        data = json.loads(res.stdout)
        return data.get("streams", [])
    except Exception as e:
        logger.error(f"Failed to parse ffprobe json: {e}")
        return []


def check_audio_language(streams: list[dict[str, Any]], lang_spec: LanguageSpec) -> bool:
    """
    Check if video already has a specified language
    """
    for s in streams:
        if s.get("codec_type") == "audio":                                                                                                                                        
                tags = s.get("tags", {})
                lang = tags.get("language", "").lower()
                title = tags.get("title", "").lower()

                if lang in (lang_spec.code_3, lang_spec.code_2):
                    return True
                if any(kw in title for kw in lang_spec.keywords):
                    return True
    return False


def determine_audio_layout(
    audio_streams: list[dict[str, Any]],
    is_mp4: bool,
    bitrate_51: str = "448k",
    bitrate_stereo: str = "256k",
) -> AudioLayout:
    """
    Determine target layout and bitrates.
    MKV with >= 6 channels gets AC3 5.1; MP4 or <= 2 channels gets Stereo.
    """
    primary_channels = 2
    if audio_streams:
        primary_channels = audio_streams[0].get("channels", 2)

    if primary_channels >= 6 and not is_mp4:
        return AudioLayout(
            layout="5.1",
            channels=6,
            bitrate=bitrate_51,
            title_suffix="5.1",
        )
    return AudioLayout(
        layout="stereo",
        channels=2,
        bitrate=bitrate_stereo,
        title_suffix="Stereo",
    )


def probe_media(
    video_path: str | Path,
    bitrate_51: str = "448k",
    bitrate_stereo: str = "256k",
    lang: str = "pol",
) -> MediaInfo:
    v_path = str(video_path)
    ext = Path(v_path).suffix.lower()
    is_mp4 = ext in MP4_EXTENSIONS

    duration = get_video_duration(v_path)
    streams = probe_streams(v_path)

    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    if not audio_streams:
        raise ValueError(f"File {v_path} contains no audio streams.")

    lang_spec = resolve_language(lang)
    has_target = check_audio_language(streams, lang_spec)
    layout = determine_audio_layout(audio_streams, is_mp4, bitrate_51, bitrate_stereo)

    safe_sub_indices = [
        s.get("index")
        for s in subtitle_streams
        if s.get("codec_name", "").lower() in SAFE_SUBTITLE_CODECS and s.get("index") is not None
    ]

    return MediaInfo(
        path=v_path,
        duration=duration,
        streams=streams,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
        has_target_audio=has_target,
        audio_layout=layout,
        safe_sub_indices=safe_sub_indices,
    )
