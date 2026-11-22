"""
Batched audio mixing engine.
Generates raw PCM sparse buffers for dialogue cues, handles boundary carryover,
applies dynamic sidechain ducking, and encodes final surround or stereo audio.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from subdub.core.probe import AudioLayout
from subdub.core.tts import batch_decode_cues

logger = logging.getLogger("subdub.mixer")


def extract_background_audio(
    video_path: str | Path,
    output_w64: str | Path,
    layout: AudioLayout,
    sample_rate: int = 48000,
) -> bool:
    """Extract and resample primary background audio stream to Wave64 PCM."""
    logger.info(f"Extracting background audio ({layout.title_suffix}) to Wave64 PCM...")
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-y",
        "-threads", "2",
        "-err_detect", "ignore_err",
        "-fflags", "+genpts",
        "-i", str(video_path),
        "-vn", "-sn",
        "-map", "0:a:0",
        "-af", f"aresample={sample_rate}:ochl={layout.layout}:async=1:first_pts=0",
        "-c:a", "pcm_s16le",
        str(output_w64),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.isfile(output_w64):
        logger.error(f"Failed to extract background audio: {res.stderr[-500:]}")
        return False
    return True


def mix_batched_audio(
    video_path: str | Path,
    cues: list[dict[str, Any]],
    work_dir: str | Path,
    layout: AudioLayout,
    duration: float,
    is_mp4: bool,
    batch_seconds: float = 900.0,
    sample_rate: int = 48000,
    ducking_threshold: float = 0.025,
    ducking_ratio: float = 4.0,
    ducking_attack: int = 25,
    ducking_release: int = 250,
) -> str | None:
    """
    Mix dialogue cues with background audio in 15-minute time windows.
    Returns path to encoded final audio track (.mka or .m4a), or None on error.
    """
    w_dir = Path(work_dir)
    w_dir.mkdir(parents=True, exist_ok=True)

    bytes_per_sec = sample_rate * 2 * 2  # 192,000 B/s (48kHz, 16-bit, stereo)
    bg_w64 = w_dir / "bg_full.w64"

    if not extract_background_audio(video_path, bg_w64, layout, sample_rate):
        return None

    num_batches = max(1, int((duration + batch_seconds - 1) // batch_seconds))
    logger.info(
        f"Mixing audio in {num_batches} batches of {int(batch_seconds // 60)} minutes..."
    )

    chunk_files: list[str] = []
    carryover_pcm = b""

    try:
        # Mix batches
        for b_idx in range(num_batches):
            b_start = b_idx * batch_seconds
            b_dur = min(batch_seconds, duration - b_start)
            if b_dur <= 0.05:
                break

            b_end = b_start + b_dur
            batch_bytes = int(round(b_dur * bytes_per_sec))
            batch_bytes -= batch_bytes % 4
            if batch_bytes <= 0:
                break

            lek_chunk_raw = w_dir / f"lek_chunk_{b_idx:03d}.raw"
            mix_chunk_w64 = w_dir / f"mix_chunk_{b_idx:03d}.w64"

            with open(lek_chunk_raw, "wb") as f_raw:
                f_raw.truncate(batch_bytes)

            batch_cues = [c for c in cues if b_start <= c["start"] < b_end]

            with open(lek_chunk_raw, "r+b") as f_raw:
                if carryover_pcm:
                    to_write = carryover_pcm[:batch_bytes]
                    carryover_pcm = carryover_pcm[batch_bytes:]
                    f_raw.seek(0)
                    f_raw.write(to_write)

                if batch_cues:
                    pcms = batch_decode_cues(batch_cues, sample_rate, max_workers=2)
                    for cue, pcm in zip(batch_cues, pcms):
                        if not pcm:
                            continue
                        offset = int((cue["start"] - b_start) * bytes_per_sec)
                        offset -= offset % 4
                        if offset >= batch_bytes:
                            continue
                        space_left = batch_bytes - offset
                        if len(pcm) > space_left:
                            carryover_pcm = pcm[space_left:]
                            pcm = pcm[:space_left]
                        f_raw.seek(offset)
                        f_raw.write(pcm)

            if layout.channels == 6:
                lek_filter = (
                    "[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    "pan=5.1|FC=0.7*c0+0.7*c1|FL=0.25*c0|FR=0.25*c1,"
                    "asplit=2[lek_sc][lek_mix]"
                )
            else:
                lek_filter = (
                    "[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    "asplit=2[lek_sc][lek_mix]"
                )

            chunk_filter = (
                f"[0:a]aformat=sample_fmts=fltp:channel_layouts={layout.layout}[bg];"
                f"{lek_filter};"
                f"[bg][lek_sc]sidechaincompress=threshold={ducking_threshold}:"
                f"ratio={ducking_ratio}:attack={ducking_attack}:release={ducking_release}[ducked];"
                f"[ducked][lek_mix]amix=inputs=2:duration=first:weights=1.0 1.35:normalize=0:dropout_transition=0[outa]"
            )

            mix_cmd = [
                "ffmpeg",
                "-v", "error",
                "-y",
                "-filter_complex_threads", "2",
                "-threads", "2",
                "-ss", f"{b_start:.6f}",
                "-t", f"{b_dur:.6f}",
                "-i", str(bg_w64),
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", "2",
                "-i", str(lek_chunk_raw),
                "-filter_complex", chunk_filter,
                "-map", "[outa]",
                "-c:a", "pcm_s16le",
                str(mix_chunk_w64),
            ]

            res = subprocess.run(mix_cmd, capture_output=True, text=True)
            if lek_chunk_raw.exists():
                lek_chunk_raw.unlink()

            if res.returncode != 0 or not mix_chunk_w64.is_file():
                logger.error(f"Mixing batch {b_idx + 1}/{num_batches} failed: {res.stderr[-500:]}")
                return None

            chunk_files.append(str(mix_chunk_w64))
            logger.info(f"  -> Batch [{b_idx + 1}/{num_batches}] mixed successfully.")

        if bg_w64.exists():
            bg_w64.unlink()

        # Concat chunks and encode to AC3 or AAC
        concat_list_path = w_dir / "chunks.txt"
        with open(concat_list_path, "w", encoding="utf-8") as f_list:
            for cf in chunk_files:
                f_list.write(f"file '{cf}'\n")

        if is_mp4:
            final_audio = w_dir / "lektor_final.m4a"
            out_codec = "aac"
        else:
            final_audio = w_dir / "lektor_final.mka"
            out_codec = "ac3"

        logger.info(
            f"Concatenating batches and encoding {out_codec.upper()} ({layout.bitrate})..."
        )
        encode_cmd = [
            "ffmpeg",
            "-v", "error",
            "-y",
            "-threads", "2",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c:a", out_codec,
            "-ac", str(layout.channels),
            "-b:a", layout.bitrate,
            str(final_audio),
        ]
        res = subprocess.run(encode_cmd, capture_output=True, text=True)

        # Cleanup
        for cf in chunk_files:
            cf_p = Path(cf)
            if cf_p.exists():
                cf_p.unlink()

        if res.returncode != 0 or not final_audio.is_file():
            logger.error(f"Encoding {out_codec.upper()} failed: {res.stderr[-500:]}")
            return None

        return str(final_audio)

    finally:
        # Cleanup v2
        if bg_w64.exists():
            bg_w64.unlink()
        for cf in chunk_files:
            cf_p = Path(cf)
            if cf_p.exists():
                cf_p.unlink()
