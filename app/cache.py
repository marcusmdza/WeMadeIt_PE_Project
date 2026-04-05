import json
import logging
import os

import redis

from app.metrics_store import increment_cache_hit, increment_cache_miss

logger = logging.getLogger(__name__)

_TTL_SECONDS = 300  # 5 minutes

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            decode_responses=True,
        )
    return _client


def get_cached_url(short_code):
    """Return cached URL dict for short_code, or None on miss or Redis failure."""
    try:
        data = _get_client().get(f"url:{short_code}")
        if data is not None:
            increment_cache_hit()
            return json.loads(data)
    except Exception:
        logger.warning("Redis unavailable — cache get skipped for %s", short_code)
    increment_cache_miss()
    return None


def cache_url(short_code, url_data):
    """Store url_data dict in Redis with a 5-minute TTL. Fails silently."""
    try:
        _get_client().setex(f"url:{short_code}", _TTL_SECONDS, json.dumps(url_data))
    except Exception:
        logger.warning("Redis unavailable — cache set skipped for %s", short_code)


def invalidate_url(short_code):
    """Delete the cached entry for short_code. Fails silently."""
    try:
        _get_client().delete(f"url:{short_code}")
    except Exception:
        logger.warning("Redis unavailable — cache invalidation skipped for %s", short_code)
