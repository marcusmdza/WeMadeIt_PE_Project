"""
Health checks and Discord alerting.

CLI usage:
    flask check-alerts

Cron example (runs every 5 minutes inside the container):
    */5 * * * * cd /app && flask check-alerts
"""

import json
import logging
import os
import threading
import time
import urllib.request
from collections import deque

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error-rate spike detection
# ---------------------------------------------------------------------------
# Sliding window: timestamps of recent 4xx/5xx responses.
_ERROR_WINDOW_SECONDS = 60
_ERROR_THRESHOLD = 10
_recent_errors: deque[float] = deque()
_alert_lock = threading.Lock()
# Suppress repeated alerts: only fire once per window until errors clear.
_last_alert_sent: list[float] = [0.0]


def record_error_and_maybe_alert() -> None:
    """Call from after_request when status >= 400. Fires an alert if the
    error rate exceeds _ERROR_THRESHOLD errors in _ERROR_WINDOW_SECONDS."""
    now = time.time()
    with _alert_lock:
        _recent_errors.append(now)
        # Evict timestamps outside the window.
        cutoff = now - _ERROR_WINDOW_SECONDS
        while _recent_errors and _recent_errors[0] < cutoff:
            _recent_errors.popleft()

        count = len(_recent_errors)
        if count >= _ERROR_THRESHOLD:
            # Only re-alert once per window to avoid flooding Discord.
            if now - _last_alert_sent[0] >= _ERROR_WINDOW_SECONDS:
                _last_alert_sent[0] = now
                message = (
                    f":warning: High error rate: {count} errors in the last "
                    f"{_ERROR_WINDOW_SECONDS}s"
                )
                # Run in a background thread so it never blocks the request.
                threading.Thread(
                    target=send_discord_alert, args=(message,), daemon=True
                ).start()


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def check_health() -> dict:
    """Return a dict with 'db' and 'redis' connectivity status strings."""
    statuses = {}

    # Database
    try:
        from app.database import db
        db.execute_sql("SELECT 1")
        statuses["db"] = "connected"
    except Exception as exc:
        statuses["db"] = f"disconnected: {exc}"

    # Redis
    try:
        from app.cache import _get_client
        _get_client().ping()
        statuses["redis"] = "connected"
    except Exception as exc:
        statuses["redis"] = f"disconnected: {exc}"

    return statuses


# ---------------------------------------------------------------------------
# Discord webhook
# ---------------------------------------------------------------------------

def send_discord_alert(message: str) -> None:
    """POST message to the Discord webhook. Falls back to logging if the env
    var is not set or the request fails."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("ALERT (no webhook configured): %s", message)
        return

    payload = json.dumps({"content": message}).encode()
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 204):
                logger.error("Discord webhook returned HTTP %s", resp.status)
    except Exception as exc:
        logger.error("Failed to send Discord alert: %s", exc)


# ---------------------------------------------------------------------------
# Flask CLI command
# ---------------------------------------------------------------------------

def register_cli(app) -> None:
    @app.cli.command("check-alerts")
    def check_alerts_command():
        """Check DB and Redis health; send a Discord alert if anything is down."""
        statuses = check_health()
        down = {svc: msg for svc, msg in statuses.items() if not msg.startswith("connected")}

        if down:
            details = ", ".join(f"{svc}: {msg}" for svc, msg in down.items())
            message = f":red_circle: Service degraded — {details}"
            logger.warning(message)
            send_discord_alert(message)
            print(f"ALERT sent: {message}")
        else:
            print("All services healthy:", statuses)
