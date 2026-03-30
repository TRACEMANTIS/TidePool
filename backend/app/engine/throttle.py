"""Redis-based token-bucket rate limiter for email sends."""

from __future__ import annotations

import asyncio
import logging
import math
import time

logger = logging.getLogger(__name__)

# Redis key prefix for throttle state.
_KEY_PREFIX = "tidepool:throttle"

# Lua script implementing an atomic token-bucket acquire.
# Keys: [bucket_key]
# Args: [max_tokens, refill_rate_per_sec, now_ts]
# Returns: 1 if a token was acquired, 0 otherwise.
_ACQUIRE_LUA = """
local key          = KEYS[1]
local max_tokens   = tonumber(ARGV[1])
local refill_rate  = tonumber(ARGV[2])
local now          = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens      = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    -- First call: initialise the bucket.
    tokens = max_tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 86400)
    return 1
end

-- Refill tokens based on elapsed time.
local elapsed = now - last_refill
local refill  = elapsed * refill_rate
tokens = math.min(max_tokens, tokens + refill)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 86400)
    return 1
else
    redis.call('HSET', key, 'last_refill', now)
    redis.call('EXPIRE', key, 86400)
    return 0
end
"""

# Redis key for campaign send counters.
_COUNTER_KEY_PREFIX = "tidepool:campaign_counters"


class SendThrottle:
    """Rate limiter for outbound email sends using a Redis token bucket.

    Parameters
    ----------
    rate_per_minute:
        Maximum number of emails to send per minute.
    redis_client:
        An ``aioredis``-compatible async Redis client (or ``redis.asyncio``).
    campaign_id:
        Campaign identifier -- used to namespace the Redis keys.
    """

    def __init__(
        self,
        rate_per_minute: int,
        redis_client,
        campaign_id: int,
    ) -> None:
        self.rate_per_minute = max(1, rate_per_minute)
        self.redis = redis_client
        self.campaign_id = campaign_id
        self._bucket_key = f"{_KEY_PREFIX}:{campaign_id}"
        self._script_sha: str | None = None
        # Refill rate expressed as tokens per second.
        self._refill_rate = self.rate_per_minute / 60.0
        # Max burst -- allow up to 1 minute's worth of tokens.
        self._max_tokens = self.rate_per_minute

    async def _ensure_script(self) -> str:
        """Load the Lua script into Redis and cache its SHA."""
        if self._script_sha is None:
            self._script_sha = await self.redis.script_load(_ACQUIRE_LUA)
        return self._script_sha

    async def acquire(self) -> None:
        """Block until a send slot is available.

        Uses exponential back-off between polls to avoid hammering Redis
        when the bucket is empty.  The initial poll interval is ~10 ms and
        caps at 500 ms.
        """
        sha = await self._ensure_script()
        backoff = 0.01  # 10 ms initial
        max_backoff = 0.5

        while True:
            now = time.time()
            acquired = await self.redis.evalsha(
                sha,
                1,
                self._bucket_key,
                str(self._max_tokens),
                str(self._refill_rate),
                str(now),
            )
            if int(acquired) == 1:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    async def get_current_rate(self) -> float:
        """Return the approximate actual send rate (sends/minute) based on
        Redis counters for this campaign.

        If no counter data is available, returns 0.0.
        """
        counter_key = f"{_COUNTER_KEY_PREFIX}:{self.campaign_id}"
        data = await self.redis.hgetall(counter_key)
        if not data:
            return 0.0

        sent = int(data.get(b"sent", data.get("sent", 0)))
        start_ts = float(data.get(b"start_ts", data.get("start_ts", 0)))
        if start_ts == 0 or sent == 0:
            return 0.0

        elapsed_minutes = (time.time() - start_ts) / 60.0
        if elapsed_minutes <= 0:
            return 0.0
        return sent / elapsed_minutes

    async def cleanup(self) -> None:
        """Remove the throttle bucket key from Redis."""
        await self.redis.delete(self._bucket_key)


def calculate_throttle(total_recipients: int, window_hours: float) -> int:
    """Calculate the required sends-per-minute rate to deliver
    *total_recipients* emails within *window_hours*.

    Returns at least 1 and at most 10,000 emails per minute.

    Parameters
    ----------
    total_recipients:
        Total number of emails to send.
    window_hours:
        Time window in hours to spread the sends across.

    Returns
    -------
    int
        Target rate in emails per minute.
    """
    if window_hours <= 0:
        return min(10_000, max(1, total_recipients))
    window_minutes = window_hours * 60.0
    rate = math.ceil(total_recipients / window_minutes)
    return max(1, min(10_000, rate))
