"""
Command-Line Interface for subdub.
Handles single file processing, batch directory scanning, and daemon/server mode.
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import sys
import time
from pathlib import Path

from subdub.config import is_path_excluded, load_config
from subdub.core.pipeline import process_video
from subdub.core.probe import SUPPORTED_VIDEO_EXTENSIONS, check_audio_language, probe_streams
from subdub.core.subtitles import find_or_extract_srt
from subdub.server import run_server

from subdub.core.languages import resolve_language

logger = logging.getLogger("subdub")


def setup_logging(verbose: bool = False) -> None:
    """Initialize structured console logging"""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] [subdub] %(message)s"
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def acquire_instance_lock(lock_file_path: str):
    """
    Acquire non-blocking flock to guarantee single active instance.
    Returns open file descriptor or None if another instance is running.
    """
    lock_path = Path(lock_file_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fp = open(lock_path, "w")
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fp
    except (BlockingIOError, OSError):
        return None


def run_scan_mode(dirs: list[str], config, process_all: bool = False, lang: str = "pol") -> int:
    """
    Scan directories for movies and episodes lacking Polish audio.
    """
    lang_spec = resolve_language(lang)
    exclude_dirs = config.exclude_dirs
    active_dirs = []
    for d in dirs:
        if is_path_excluded(d, exclude_dirs):
            logger.info(f"Skipping excluded scan directory: {d}")
        else:
            active_dirs.append(d)

    dirs=active_dirs
    logger.info(f"Scanning directories: {dirs}")
    processed_count = 0

    while True:
        found_target = False
        for sdir in dirs:
            if not os.path.isdir(sdir):
                logger.debug(f"Scan directory not found: {sdir}")
                continue

            for root, dirnames, files in os.walk(sdir):
                dirnames[:] = [
                    d for d in dirnames
                    if not is_path_excluded(os.path.join(root, d), exclude_dirs)
                ]
                for f in sorted(files):
                    f_lower = f.lower()
                    if (
                        not f_lower.endswith(SUPPORTED_VIDEO_EXTENSIONS)
                        or ".tmp_lektor." in f_lower
                        or f.startswith(".")
                    ):
                        continue

                    vpath = os.path.join(root, f)
                    streams = probe_streams(vpath)
                    has_target = check_audio_language(streams, lang_spec)
                    if has_target and not config.force:
                        continue

                    srt_path = find_or_extract_srt(
                        video_path=vpath,
                        streams=streams,
                        temp_dir=config.temp_dir,
                        lang=config.lang,
                    )
                    if srt_path:
                        found_target = True
                        logger.info(f"Found media without Polish audio: {f}")
                        ok = process_video(vpath, config, explicit_subs=srt_path)
                        processed_count += 1

                        if not process_all:
                            logger.info(
                                "Finished single job (default cron mode). Exiting."
                            )
                            return 0 if ok else 1

                        time.sleep(3)
                        break

                if found_target and process_all:
                    break
            if found_target and process_all:
                break

        if not found_target:
            if processed_count > 0:
                logger.info(
                    f"Scan complete! Processed {processed_count} files. No more pending items."
                )
            else:
                logger.info(
                    f"All items with subtitles already have {lang_spec.name} audio. Nothing to do."
                )
            break

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="subdub",
        description="Lightweight AI voice-over (TTS) generator and remuxer for video media.",
    )
    parser.add_argument(
        "video",
        nargs="?",
        help="Path to video file (.mkv or .mp4) to process.",
    )
    parser.add_argument(
        "--subs",
        help="Explicit path to subtitle file (.srt).",
    )
    parser.add_argument(
        "--scan",
        nargs="?",
        const="DEFAULT",
        help="Scan directory for media without audio (defaults to scan_dirs in config).",
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="In scan mode, process all pending files instead of stopping after the first one.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the background HTTP Webhook server for Bazarr integration.",
    )
    parser.add_argument(
        "--host",
        help="Bind address for the webhook server (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port for the webhook server (default: 9999).",
    )
    parser.add_argument(
        "--voice",
        help="Override TTS voice model (e.g. pl-PL-MarekNeural, pl-PL-AgnieszkaNeural).",
    )
    parser.add_argument(
        "--lang",
        help="Override subtitle and audio track language code (default: pol).",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Process video even if it already contains target audio.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without generating speech or modifying files.",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to custom config.toml file.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load configuration Defaults -> config.toml -> CLI flags
    cli_overrides = {
        "voice": args.voice,
        "lang": args.lang,
        "force": args.force if args.force else None,
        "dry_run": args.dry_run if args.dry_run else None,
        "server_host": args.host,
        "server_port": args.port,
    }
    config = load_config(args.config, **cli_overrides)

    # Mode 1: Webhook server
    if args.serve:
        run_server(config)
        return

    # Mode 2: Directory scan
    if args.scan:
        scan_dirs = (
            config.scan_dirs
            if args.scan == "DEFAULT"
            else [args.scan]
        )
        exit_code = run_scan_mode(scan_dirs, config, process_all=args.all, lang=config.lang)
        sys.exit(exit_code)

    # Mode 3: Single file
    if args.video:
        ok = process_video(args.video, config, explicit_subs=args.subs)
        sys.exit(0 if ok else 1)

    # No arguments provided
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
