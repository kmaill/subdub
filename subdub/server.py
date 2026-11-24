"""
Webhook Server with FIFO Job Queue for Bazarr.
"""

from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from subdub.config import Config
from subdub.core.pipeline import process_video
from subdub.core.probe import SUPPORTED_VIDEO_EXTENSIONS

logger = logging.getLogger("subdub.server")


class JobQueue:
    """FIFO queue with a single sequential worker thread."""

    def __init__(self, config: Config):
        self.config = config
        self._q: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def enqueue(self, video_path: str, subs_path: str | None = None) -> int:
        """Enqueue task and return current queue size."""
        self._q.put((video_path, subs_path))
        return self._q.qsize()

    @property
    def size(self) -> int:
        return self._q.qsize()

    def _worker_loop(self) -> None:
        logger.info("Worker thread initialized. Waiting for jobs...")
        while not self._stop_event.is_set():
            try:
                item = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            video_path, subs_path = item
            logger.info(f"[QUEUE] Starting job: {video_path} (Remaining in queue: {self._q.qsize()})")
            try:
                process_video(video_path, self.config, explicit_subs=subs_path, blocking_lock=True)
            except Exception as e:
                logger.error(f"[QUEUE] Error processing {video_path}: {e}", exc_info=True)
            finally:
                self._q.task_done()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._worker_thread.join(timeout=3.0)


def extract_media_path_from_payload(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Extract video path and optional subtitles path from Bazarr, Radarr and Sonarr.
    """
    video_path = None
    subs_path = None

    # Check direct fields
    for key in (
        "video",
        "video_path",
        "episode",
        "episode_path",
        "movie",
        "movie_path",
        "file",
        "path",
        "folderPath",
    ):
        if key in payload and isinstance(payload[key], str) and payload[key].strip():
            video_path = payload[key].strip()
            break

    for key in ("subtitles", "subs", "subs_path", "subtitle_path"):
        if key in payload and isinstance(payload[key], str) and payload[key].strip():
            subs_path = payload[key].strip()
            break

    if not video_path:
        for nested_key in ("episodeFile", "movieFile", "series", "movie"):
            nested_obj = payload.get(nested_key)
            if isinstance(nested_obj, dict) and isinstance(nested_obj.get("path"), str):
                video_path = nested_obj["path"].strip()
                break
            if isinstance(nested_obj, dict) and isinstance(nested_obj.get("folderPath"), str): # i think it works
                video_path = nested_obj["folderPath"].strip()
                break
    
    # Check JSON notification format
    if not video_path and "message" in payload and isinstance(payload["message"], str):
        msg = payload["message"].strip()
        # If message looks like a file path or JSON string
        if msg.startswith("{") and msg.endswith("}"):
            try:
                sub_dict = json.loads(msg)
                return extract_media_path_from_payload(sub_dict)
            except Exception:
                pass
        elif msg.endswith(SUPPORTED_VIDEO_EXTENSIONS):
            video_path = msg

    return video_path, subs_path


def make_webhook_handler(job_queue: JobQueue):
    """Factory to create request handler with injected job queue."""

    class WebhookHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            # Route HTTP server logs to standard logger
            logger.debug(f"{self.client_address[0]} - {format % args}")

        def _send_json_response(self, status_code: int, data: dict[str, Any]) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/health", "/status"):
                self._send_json_response(200, {
                    "status": "healthy",
                    "service": "subdub",
                    "queue_size": job_queue.size,
                })
            else:
                self._send_json_response(404, {"error": "Not Found"})

        def do_POST(self) -> None:
            if self.path not in ("/webhook", "/webhook/"):
                self._send_json_response(404, {"error": "Not Found"})
                return

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_json_response(400, {"error": "Empty body"})
                return

            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json_response(400, {"error": f"Invalid JSON payload: {e}"})
                return

            video_path, subs_path = extract_media_path_from_payload(payload)
            if not video_path:
                logger.warning(f"Received webhook with unrecognized payload: {payload}")
                self._send_json_response(422, {
                    "error": "Could not identify video path in payload",
                    "received": payload,
                })
                return

            qsize = job_queue.enqueue(video_path, subs_path)
            logger.info(f"Accepted webhook for '{video_path}' (Queue position: {qsize})")

            self._send_json_response(202, {
                "status": "accepted",
                "video": video_path,
                "queue_size": qsize,
            })

    return WebhookHandler


def run_server(config: Config) -> None:
    host = config.server_host
    port = config.server_port
    job_queue = JobQueue(config)
    handler_class = make_webhook_handler(job_queue)

    server = ThreadingHTTPServer((host, port), handler_class)
    logger.info(f"Subdub Webhook Server listening on http://{host}:{port}/webhook")
    logger.info("Ready to accept notifications from Bazarr/Sonarr/Radarr.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Webhook Server...")
    finally:
        server.server_close()
        job_queue.shutdown()
        logger.info("Server stopped.")
