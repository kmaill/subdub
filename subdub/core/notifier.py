"""
Post-processing notifications.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

logger = logging.getLogger("subdub.notifier")


def notify_jellyfin(url: str, token: str, timeout: float = 5.0) -> bool:
    """Send POST /Library/Refresh to Jellyfin server."""
    if not url:
        return False

    endpoint = f"{url.rstrip('/')}/Library/Refresh"
    headers: dict[str, str] = {}
    if token:
        headers["X-Emby-Token"] = token

    try:
        req = urllib.request.Request(endpoint, data=b"", headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            logger.info(f"Notified Jellyfin library refresh (status: {resp.status})")
            return resp.status in (200, 204)
    except Exception as e:
        logger.warning(f"Failed to notify Jellyfin at {endpoint}: {e}")
        return False
