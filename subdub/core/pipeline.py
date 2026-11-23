"""
Processing pipeline for subdub.
Coordinates pre-flight checks, subtitles, speech synthesis, batched mixing, and remuxing.
"""

from __future__ import annotations

import fcntl
import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from subdub.config import Config
from subdub.core.mixer import mix_batched_audio
from subdub.core.notifier import notify_jellyfin
from subdub.core.probe import MP4_EXTENSIONS, probe_media
from subdub.core.remuxer import remux_and_replace
from subdub.core.subtitles import find_or_extract_srt, parse_srt
from subdub.core.tts import generate_cues_audio

logger = logging.getLogger("subdub.pipeline")


def process_video(
    video_path: str | Path,
    config: Config,
    explicit_subs: str | Path | None = None,
    blocking_lock: bool = False,
) -> bool:
    """
    Run the pipeline on a single video file.
    Returns True on success or expected skip, False on error.
    """
    v_path = Path(video_path).resolve()
    if not v_path.is_file():
        logger.error(f"Video file does not exist: {v_path}")
        return False

    logger.info(f"=== PROCESSING VIDEO: {v_path.name} ===")

    try:
        info = probe_media(
            v_path,
            bitrate_51=config.bitrate_51,
            bitrate_stereo=config.bitrate_stereo,
            lang=config.lang,
        )
    except Exception as e:
        logger.error(f"Failed to probe {v_path.name}: {e}")
        return False

    if info.has_target_audio and not config.force:
        logger.info(
            f"[SKIP] Video already contains {config.lang} audio (use --force to override): {v_path.name}"
        )
        return True

    # Ensure temp base directory exists
    temp_base = Path(config.temp_dir)
    temp_base.mkdir(parents=True, exist_ok=True)

    srt_path = find_or_extract_srt(
        video_path=v_path,
        streams=info.streams,
        temp_dir=temp_base,
        explicit_subs=explicit_subs,
        lang=config.lang,
    )
    if not srt_path:
        logger.info(f"[SKIP] No matching subtitles found for {v_path.name}.")
        return True

    cues = parse_srt(srt_path, strip_sdh=config.strip_sdh)
    if not cues:
        logger.warning(f"No valid dialogue cues found in {srt_path}.")
        return False

    logger.info(f"Found {len(cues)} dialogue cues in subtitles.")

    if config.dry_run:
        logger.info(f"[DRY-RUN] Would generate AI voice-over for {v_path.name} ({len(cues)} cues).")
        return True

    # Acquire instance lock right before TTS cue generation and audio mixing
    lock_path = Path(config.lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = fcntl.LOCK_EX if blocking_lock else (fcntl.LOCK_EX | fcntl.LOCK_NB)

    lock_fp = None
    try:
        lock_fp = open(lock_path, "w")
        fcntl.flock(lock_fp, flags)
    except (BlockingIOError, OSError):
        logger.info(
            f"Another subdub job is currently processing media. Skipping {v_path.name} for now."
        )
        if lock_fp:
            try:
                lock_fp.close()
            except Exception:
                pass
        return False

    try:
        with tempfile.TemporaryDirectory(dir=str(temp_base), prefix="subdub_task_") as work_dir:
            # TTS generation
            voice_short_name = config.voice.replace("pl-PL-", "").replace("Neural", "")
            generate_cues_audio(
                cues=cues,
                cache_dir=work_dir,
                voice=config.voice,
                rate=config.rate,
                volume=config.volume,
                pitch=config.pitch,
                max_concurrency=config.max_tts_concurrency,
            )

            # Batched mixing
            is_mp4 = v_path.suffix.lower() in MP4_EXTENSIONS
            final_audio = mix_batched_audio(
                video_path=v_path,
                cues=cues,
                work_dir=work_dir,
                layout=info.audio_layout,
                duration=info.duration,
                is_mp4=is_mp4,
                batch_seconds=config.batch_seconds,
                sample_rate=config.sample_rate,
                ducking_threshold=config.ducking_threshold,
                ducking_ratio=config.ducking_ratio,
                ducking_attack=config.ducking_attack,
                ducking_release=config.ducking_release,
            )
            if not final_audio:
                logger.error("Audio mixing failed.")
                return False

            ok = remux_and_replace(
                video_path=v_path,
                final_audio=final_audio,
                temp_dir=work_dir,
                audio_streams=info.audio_streams,
                safe_sub_indices=info.safe_sub_indices,
                layout=info.audio_layout,
                prefer_mkvmerge=True,
                voice_name=voice_short_name,
                lang=config.lang,
            )
            if not ok:
                return False

        # Notification
        if config.jellyfin_enabled:
            notify_jellyfin(config.jellyfin_url, config.jellyfin_token)

        return True
    finally:
        if lock_fp:
            try:
                fcntl.flock(lock_fp, fcntl.LOCK_UN)
                lock_fp.close()
            except Exception:
                pass
