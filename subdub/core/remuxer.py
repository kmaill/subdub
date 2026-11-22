"""
Container remuxer, executes safe rendering.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from subdub.core.probe import AudioLayout, MP4_EXTENSIONS

logger = logging.getLogger("subdub.remuxer")


def remux_mkv_mkvmerge(
    video_path: str | Path,
    final_audio: str | Path,
    output_path: str | Path,
    audio_streams: list[dict[str, Any]],
    layout: AudioLayout,
    voice_name: str = "Marek",
) -> bool:
    """Remux MKV container using mkvmerge."""
    unset_defaults: list[str] = []
    for idx_i, s in enumerate(audio_streams):
        tid = s.get("index") if isinstance(s, dict) and "index" in s else (idx_i + 1)
        unset_defaults.extend(["--default-track-flag", f"{tid}:no"])

    track_name = f"Polski (Lektor AI - {voice_name} {layout.title_suffix})"
    cmd = [
        "mkvmerge",
        "-q",
        "-o", str(output_path),
        *unset_defaults,
        str(video_path),
        "--language", "0:pol",
        "--track-name", f"0:{track_name}",
        "--default-track-flag", "0:yes",
        str(final_audio),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    # mkvmerge returns 0 for success, 1 for warnings (e.g. non-critical syntax), >=2 for errors
    if res.returncode not in (0, 1) or not os.path.isfile(output_path):
        err_msg = (res.stderr or res.stdout)[-500:]
        logger.error(f"mkvmerge remux failed (code {res.returncode}): {err_msg}")
        return False
    return True


def remux_ffmpeg(
    video_path: str | Path,
    final_audio: str | Path,
    output_path: str | Path,
    audio_streams: list[dict[str, Any]],
    safe_sub_indices: list[int],
    layout: AudioLayout,
    is_mp4: bool,
    voice_name: str = "Marek",
) -> bool:
    map_args = ["-map", "0:v:0"]
    codec_args = ["-c:v", "copy"]

    for i in range(len(audio_streams)):
        map_args.extend(["-map", f"0:a:{i}"])
        codec_args.extend([f"-c:a:{i}", "copy"])

    new_track_idx = len(audio_streams)
    map_args.extend(["-map", "1:a:0"])
    track_name = f"Polski (Lektor AI - {voice_name} {layout.title_suffix})"

    codec_args.extend([
        f"-c:a:{new_track_idx}", "copy",
        f"-metadata:s:a:{new_track_idx}", "language=pol",
        f"-metadata:s:a:{new_track_idx}", f"title={track_name}",
        f"-disposition:a:{new_track_idx}", "default",
        "-disposition:a:0", "0",
    ])

    for s_idx in safe_sub_indices:
        map_args.extend(["-map", f"0:{s_idx}"])
    if safe_sub_indices:
        sub_codec = "mov_text" if is_mp4 else "copy"
        codec_args.extend(["-c:s", sub_codec])

    cmd = [
        "ffmpeg",
        "-v", "error",
        "-y",
        "-fflags", "+genpts",
        "-i", str(video_path),
        "-i", str(final_audio),
        *map_args,
        *codec_args,
        "-avoid_negative_ts", "make_zero",
        str(output_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.isfile(output_path):
        logger.error(f"FFmpeg remux failed: {res.stderr[-500:]}")
        return False
    return True


def remux_and_replace(
    video_path: str | Path,
    final_audio: str | Path,
    temp_dir: str | Path,
    audio_streams: list[dict[str, Any]],
    safe_sub_indices: list[int],
    layout: AudioLayout,
    prefer_mkvmerge: bool = True,
    voice_name: str = "Marek",
) -> bool:
    v_path = Path(video_path).resolve()
    ext = v_path.suffix.lower()
    is_mp4 = ext in MP4_EXTENSIONS

    t_dir = Path(temp_dir)
    t_dir.mkdir(parents=True, exist_ok=True)
    temp_local_output = t_dir / f"remux_output{ext}"
    temp_target_output = v_path.parent / f"{v_path.name}.tmp_lektor{ext}"

    try:
        logger.info(f"Remuxing final video container ({ext})...")
        if not is_mp4 and prefer_mkvmerge and shutil.which("mkvmerge"):
            ok = remux_mkv_mkvmerge(
                video_path=v_path,
                final_audio=final_audio,
                output_path=temp_local_output,
                audio_streams=audio_streams,
                layout=layout,
                voice_name=voice_name,
            )
        else:
            ok = remux_ffmpeg(
                video_path=v_path,
                final_audio=final_audio,
                output_path=temp_local_output,
                audio_streams=audio_streams,
                safe_sub_indices=safe_sub_indices,
                layout=layout,
                is_mp4=is_mp4,
                voice_name=voice_name,
            )

        if not ok or not temp_local_output.is_file():
            logger.error("Remux failed. Original file unchanged.")
            return False

        # Two-stage atomic write to destination
        logger.info("Transferring remuxed video to destination storage...")
        shutil.copy2(temp_local_output, temp_target_output)
        os.replace(temp_target_output, v_path)
        logger.info(f"SUCCESS: Updated {v_path.name} with AI voice-over [{layout.title_suffix}]")
        return True

    finally:
        if temp_local_output.exists():
            try:
                temp_local_output.unlink()
            except OSError:
                pass
        if temp_target_output.exists():
            try:
                temp_target_output.unlink()
            except OSError:
                pass
