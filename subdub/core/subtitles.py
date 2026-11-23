"""
Subtitle parsing, SDH cleaning, and fallback chain resolver.
Supports external .srt files and extracting embedded text subtitles.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from subdub.core.probe import SAFE_SUBTITLE_CODECS
from subdub.core.languages import resolve_language

logger = logging.getLogger("subdub.subtitles")


def srt_time_to_seconds(time_str: str) -> float:
    """Convert SRT timestamp (HH:MM:SS,mmm or HH:MM:SS.mmm) to seconds."""
    time_str = time_str.replace(",", ".").strip()
    parts = time_str.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def clean_text(text: str, strip_sdh: bool = True) -> str:
    """
    Clean dialogue text for natural speech synthesis.
    Removes HTML tags, ASS formatting tags, speaker prefixes, leading dashes/quotes,
    and optionally SDH tags ([music], (laugh)).
    """
    # Remove HTML tags (e.g. <i>, </i>, <font ...>)
    text = re.sub(r"<[^>]+>", "", text)
    # Remove ASS/SSA formatting overrides (e.g. {\an8}, {\pos(100,200)})
    text = re.sub(r"\{[^}]+\}", "", text)

    if strip_sdh:
        # Remove bracketed descriptions e.g. [music]
        text = re.sub(r"\[.*?\]", "", text)
        # Remove parenthesized descriptions e.g. (laugh)
        text = re.sub(r"\(.*?\)", "", text)

    # Remove uppercase speaker name prefixes e.g. "JAN: Cześć" -> "Cześć"
    text = re.sub(r"^[A-Z0-9_\-\s]+:\s*", "", text)
    # Remove leading dialogue dashes/hyphens
    text = re.sub(r"^\s*[-–—]\s*", "", text)
    # Remove leading quotes
    text = re.sub(r"^\s*[»«\"\"„”']\s*", "", text)
    # Normalize whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_srt(srt_path: str | Path, strip_sdh: bool = True) -> list[dict[str, Any]]:
    """
    Parse an SRT file into a sorted list of cue dicts:
    [{'start': float, 'end': float, 'text': str}, ...]
    """
    path = Path(srt_path)
    if not path.is_file():
        logger.error(f"Subtitle file not found: {srt_path}")
        return []

    # Read with UTF-8 BOM tolerance, fallback to latin2/cp1250 if invalid utf-8
    content = ""
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin2"):
        try:
            content = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue

    if not content:
        content = path.read_text(encoding="utf-8", errors="replace")

    blocks = re.split(r"\n\s*\n", content.strip())
    cues: list[dict[str, Any]] = []
    time_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})"
    )

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue

        time_line_idx = 1 if "-->" in lines[1] else (0 if "-->" in lines[0] else -1)
        if time_line_idx == -1:
            continue

        m = time_pattern.search(lines[time_line_idx])
        if not m:
            continue

        start_sec = srt_time_to_seconds(m.group(1))
        end_sec = srt_time_to_seconds(m.group(2))
        text = " ".join(lines[time_line_idx + 1:])
        cleaned = clean_text(text, strip_sdh=strip_sdh)

        if cleaned and re.search(r"\w", cleaned):
            cues.append({"start": start_sec, "end": end_sec, "text": cleaned})

    cues.sort(key=lambda x: x["start"])
    return cues


def find_or_extract_srt(
    video_path: str | Path,
    streams: list[dict[str, Any]],
    temp_dir: str | Path,
    explicit_subs: str | Path | None = None,
    lang: str = "pol",
) -> str | None:
    """
    Fallback:
    1. Explicit file passed via explicit_subs (--subs).
    2. External .srt files matching the video base name.
    3. Embedded text subtitle stream extracted via FFmpeg into temp_dir.
    4. None if no subtitles found.
    """
    # Explicit subtitles
    if explicit_subs:
        subs_p = Path(explicit_subs)
        if subs_p.is_file() and subs_p.stat().st_size > 10:
            return str(subs_p.resolve())
        logger.warning(f"Explicit subtitles file not found or empty: {explicit_subs}")

    v_path = Path(video_path).resolve()
    v_dir = v_path.parent
    base = v_path.stem

    # Check for external subtitles alongside video
    lang_spec = resolve_language(lang)
    candidates = [
        v_dir / f"{base}.{lang_spec.code_3}.srt",
        v_dir / f"{base}.{lang_spec.code_2}.srt",
        v_dir / f"{base}.{lang_spec.code_2}.hi.srt",
        v_dir / f"{base}.srt",
    ]
    for cand in candidates:
        if cand.is_file() and cand.stat().st_size > 10:
            logger.info(f"Found external subtitles: {cand.name}")
            return str(cand)

    # Search by glob
    patterns = [
        v_dir / f"{glob.escape(base)}*.{lang_spec.code_3}*.srt",
        v_dir / f"{glob.escape(base)}*.{lang_spec.code_2}*.srt",
    ]
    for pat in patterns:
        for cand_str in glob.glob(str(pat)):
            cand_p = Path(cand_str)
            if cand_p.is_file() and cand_p.stat().st_size > 10:
                logger.info(f"Found external subtitles (glob): {cand_p.name}")
                return str(cand_p)

    # Extract embedded subtitle stream via FFmpeg
    lang_codes = {lang.lower(), "pol", "pl"}
    for s in streams:
        if s.get("codec_type") == "subtitle":
            codec = s.get("codec_name", "").lower()
            if codec not in SAFE_SUBTITLE_CODECS:
                continue

            tags = s.get("tags", {})
            s_lang = tags.get("language", "").lower()
            s_title = tags.get("title", "").lower()

            valid_langs = {lang_spec.code_3, lang_spec.code_2}                                                                                                                                
            is_match = (s_lang in valid_langs) or any(kw in s_title for kw in lang_spec.keywords)

            if is_match:
                s_index = s.get("index")
                out_srt = Path(temp_dir) / f"extracted_{base}_{s_index}.srt"
                out_srt.parent.mkdir(parents=True, exist_ok=True)

                logger.info(
                    f"Extracting embedded {lang_spec.name} subtitles stream {s_index} to temporary file..."
                )
                cmd = [
                    "ffmpeg",
                    "-v", "error",
                    "-y",
                    "-fflags", "+genpts",
                    "-i", str(v_path),
                    "-map", f"0:{s_index}",
                    str(out_srt),
                ]
                r = subprocess.run(cmd, capture_output=True)
                if r.returncode == 0 and out_srt.is_file() and out_srt.stat().st_size > 50:
                    return str(out_srt)
                else:
                    logger.warning(f"Failed to extract stream {s_index}: {r.stderr.decode()}")

    return None
