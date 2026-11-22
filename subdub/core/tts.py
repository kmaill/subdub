"""
Asynchronous speech synthesis via Microsoft Edge TTS.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import edge_tts

logger = logging.getLogger("subdub.tts")


async def generate_cues_audio_async(
    cues: list[dict[str, Any]],
    cache_dir: str | Path,
    voice: str = "pl-PL-MarekNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    max_concurrency: int = 4,
    timeout_sec: float = 25.0,
) -> None:
    """
    Fetch MP3 audio for each subtitle cue.
    """
    c_dir = Path(cache_dir)
    c_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(max_concurrency)
    done_lock = asyncio.Lock()
    done_count = 0
    total = len(cues)

    async def fetch_cue(cue: dict[str, Any], idx: int) -> None:
        nonlocal done_count
        cache_key = f"{cue['text']}_{voice}_{rate}_{volume}_{pitch}"
        h = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
        mp3_path = c_dir / f"cue_{idx:05d}_{h}.mp3"
        cue["mp3"] = str(mp3_path)

        if not (mp3_path.is_file() and mp3_path.stat().st_size > 100):
            async with sem:
                for attempt in range(1, 4):
                    try:
                        comm = edge_tts.Communicate(
                            text=cue["text"],
                            voice=voice,
                            rate=rate,
                            volume=volume,
                            pitch=pitch,
                        )
                        await asyncio.wait_for(comm.save(str(mp3_path)), timeout=timeout_sec)
                        if mp3_path.is_file() and mp3_path.stat().st_size > 100:
                            break
                    except Exception as e:
                        if mp3_path.exists():
                            try:
                                mp3_path.unlink()
                            except OSError:
                                pass
                        if attempt < 3:
                            await asyncio.sleep(attempt * 1.5)
                        else:
                            logger.warning(
                                f"Cue {idx} skipped after 3 attempts: '{cue['text']}' ({e})"
                            )

        async with done_lock:
            done_count += 1
            if done_count % 100 == 0 or done_count == total:
                pct = (done_count * 100) // max(1, total)
                logger.info(f"Downloaded [{done_count}/{total}] speech cues ({pct}%)...")

    await asyncio.gather(*(fetch_cue(cue, i) for i, cue in enumerate(cues)))


def generate_cues_audio(
    cues: list[dict[str, Any]],
    cache_dir: str | Path,
    voice: str = "pl-PL-MarekNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    max_concurrency: int = 4,
) -> None:
    """Synchronous entrypoint for speech generation."""
    if not cues:
        logger.warning("No cues provided for TTS generation.")
        return

    logger.info(
        f"Generating speech for {len(cues)} cues using voice '{voice}' (max {max_concurrency} parallel)..."
    )
    asyncio.run(
        generate_cues_audio_async(
            cues=cues,
            cache_dir=cache_dir,
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
            max_concurrency=max_concurrency,
        )
    )


def decode_mp3_to_pcm(cue: dict[str, Any], sample_rate: int = 48000) -> bytes:
    mp3 = cue.get("mp3")
    if not mp3 or not os.path.isfile(mp3) or os.path.getsize(mp3) < 100:
        return b""

    cmd = [
        "ffmpeg",
        "-v", "error",
        "-y",
        "-i", str(mp3),
        "-f", "s16le",
        "-ar", str(sample_rate),
        "-ac", "2",
        "-",
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return p.stdout


def batch_decode_cues(cues: list[dict[str, Any]], sample_rate: int = 48000, max_workers: int = 2) -> list[bytes]:
    """Decode multiple cues in parallel."""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda c: decode_mp3_to_pcm(c, sample_rate), cues))
