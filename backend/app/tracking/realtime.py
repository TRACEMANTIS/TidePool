"""Real-time campaign metrics backed by Redis.

Redis key layout
----------------
tp:campaign:{id}:counts:{event_type}   -- INCR counter per event type
tp:campaign:{id}:send_times            -- sorted set (score=timestamp) for rate calc
tp:campaign:{id}:events                -- sorted set of recent events (score=timestamp)
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)

# Maximum number of events retained in the recent-events sorted set.
_MAX_RECENT_EVENTS = 1000

# Window (seconds) over which the send rate is calculated.
_RATE_WINDOW_SECONDS = 300  # 5 minutes


class RealtimeTracker:
    """Thin async wrapper around Redis for live campaign counters and feeds."""

    def __init__(self, redis_client) -> None:
        """Initialise with an async Redis client (``redis.asyncio`` compatible)."""
        self._redis = redis_client

    # -- Key helpers --------------------------------------------------------

    @staticmethod
    def _counts_key(campaign_id: int, event_type: str) -> str:
        return f"tp:campaign:{campaign_id}:counts:{event_type}"

    @staticmethod
    def _send_times_key(campaign_id: int) -> str:
        return f"tp:campaign:{campaign_id}:send_times"

    @staticmethod
    def _events_key(campaign_id: int) -> str:
        return f"tp:campaign:{campaign_id}:events"

    # -- Atomic counter operations -----------------------------------------

    async def increment(self, campaign_id: int, event_type: str) -> int:
        """Atomically increment the counter for *event_type* and return the new value."""
        key = self._counts_key(campaign_id, event_type)
        return await self._redis.incr(key)

    async def get_live_counts(self, campaign_id: int) -> dict[str, int]:
        """Return current counts for all standard event types."""
        event_types = ["SENT", "DELIVERED", "OPENED", "CLICKED", "SUBMITTED", "REPORTED"]
        pipe = self._redis.pipeline(transaction=False)
        keys = []
        for et in event_types:
            key = self._counts_key(campaign_id, et)
            keys.append(et)
            pipe.get(key)
        values = await pipe.execute()
        return {
            et: int(v) if v is not None else 0
            for et, v in zip(keys, values)
        }

    # -- Send rate calculation ---------------------------------------------

    async def record_send_time(self, campaign_id: int) -> None:
        """Record a send timestamp for rate calculation."""
        key = self._send_times_key(campaign_id)
        now = time.time()
        pipe = self._redis.pipeline(transaction=False)
        pipe.zadd(key, {str(now): now})
        # Trim entries older than the rate window to bound memory.
        pipe.zremrangebyscore(key, "-inf", now - _RATE_WINDOW_SECONDS)
        await pipe.execute()

    async def get_send_rate(self, campaign_id: int) -> float:
        """Return the average send rate (emails per minute) over the last 5 minutes."""
        key = self._send_times_key(campaign_id)
        now = time.time()
        window_start = now - _RATE_WINDOW_SECONDS
        count = await self._redis.zcount(key, window_start, now)
        if count == 0:
            return 0.0
        # Rate = count / window in minutes.
        elapsed_minutes = _RATE_WINDOW_SECONDS / 60.0
        return round(count / elapsed_minutes, 2)

    # -- Recent event feed -------------------------------------------------

    async def push_event(self, campaign_id: int, event_data: dict) -> None:
        """Add an event to the recent-events sorted set and trim to the last 1000."""
        key = self._events_key(campaign_id)
        now = time.time()
        serialized = json.dumps(event_data, default=str)
        pipe = self._redis.pipeline(transaction=False)
        pipe.zadd(key, {serialized: now})
        # Keep only the most recent entries. ZREMRANGEBYRANK removes elements
        # from index 0 (oldest) up to (total - max - 1).
        pipe.zremrangebyrank(key, 0, -(_MAX_RECENT_EVENTS + 1))
        await pipe.execute()

    async def get_recent_events(
        self, campaign_id: int, limit: int = 50,
    ) -> list[dict]:
        """Return the most recent events, newest first."""
        key = self._events_key(campaign_id)
        # ZREVRANGE returns highest-score (newest) first.
        raw_entries = await self._redis.zrevrange(key, 0, limit - 1)
        events: list[dict] = []
        for entry in raw_entries:
            try:
                data = entry if isinstance(entry, str) else entry.decode("utf-8")
                events.append(json.loads(data))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Skipping malformed event entry in Redis")
                continue
        return events
