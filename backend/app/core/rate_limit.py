"""
Rate limit guard — async-friendly, same semantics as the original
rate_limit.py but with await support for the wait functions.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


LIMIT_KEYWORDS = (
    # Deliberately *not* a bare "429": X media filenames are 19-digit tweet
    # ids, so a plain substring match would read a healthy download line as a
    # throttle signal and abort the run every few hundred files.
    "error 429",
    "429: too many",
    "status code: 429",
    "too many requests",
    "rate limit",
    "ratelimit",
    "please wait a few minutes",
    "temporarily blocked",
    "try again later",
    "login required",
    "checkpoint",
    "challenge required",
    "feedback_required",
)


def detect_limit_signal(line: str) -> bool:
    """Whether a gallery-dl / yt-dlp output line reports throttling.

    Shared by every platform service: Instagram used to be the only caller,
    which meant X's 429s were detected by a looser private copy of this list.
    """
    return any(kw in line.lower() for kw in LIMIT_KEYWORDS)


@dataclass(slots=True)
class RateLimitPolicy:
    min_delay_seconds: int = 18
    max_delay_seconds: int = 45
    batch_size: int = 8
    batch_cooldown_seconds: int = 240
    suspected_limit_cooldown_seconds: int = 900
    jitter_seconds: int = 12
    max_limit_signals_before_stop: int = 2


def policy_from_settings() -> RateLimitPolicy:
    """Build the policy from `app.config` so the `rate_limit_*` knobs (and the
    values /api/settings reports) actually drive behaviour.

    Importing config lazily keeps this module importable from tests that have
    no settings/env loaded.
    """
    from app.config import get_settings

    s = get_settings()
    return RateLimitPolicy(
        min_delay_seconds=s.rate_limit_min_delay,
        max_delay_seconds=s.rate_limit_max_delay,
        batch_size=s.rate_limit_batch_size,
        batch_cooldown_seconds=s.rate_limit_batch_cooldown,
        suspected_limit_cooldown_seconds=s.rate_limit_limit_cooldown,
        max_limit_signals_before_stop=s.rate_limit_max_signals,
    )


class RateLimitGuard:
    def __init__(self, policy: RateLimitPolicy | None = None) -> None:
        self.policy = policy or RateLimitPolicy()
        self._processed_count = 0
        self._limit_signals = 0

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def limit_signals(self) -> int:
        return self._limit_signals

    def detect_limit_signal(self, line: str) -> bool:
        return detect_limit_signal(line)

    def record_limit_signal(self, source: str) -> bool:
        self._limit_signals += 1
        logger.warning(
            "Rate limit signal from %s (%s/%s)",
            source,
            self._limit_signals,
            self.policy.max_limit_signals_before_stop,
        )
        return self._limit_signals >= self.policy.max_limit_signals_before_stop

    async def wait_after_account(
        self, *, stop_requested: Callable[[], bool]
    ) -> None:
        self._processed_count += 1
        if self._processed_count % self.policy.batch_size == 0:
            await self._sleep_interruptibly(
                self.policy.batch_cooldown_seconds,
                stop_requested=stop_requested,
                reason="batch cooldown",
            )
            return

        delay = random.randint(
            self.policy.min_delay_seconds, self.policy.max_delay_seconds
        )
        delay += random.randint(0, self.policy.jitter_seconds)
        await self._sleep_interruptibly(
            delay, stop_requested=stop_requested, reason="rate spacing"
        )

    async def wait_after_limit_signal(
        self, *, stop_requested: Callable[[], bool]
    ) -> None:
        await self._sleep_interruptibly(
            self.policy.suspected_limit_cooldown_seconds,
            stop_requested=stop_requested,
            reason="suspected limit cooldown",
        )

    async def _sleep_interruptibly(
        self,
        seconds: int,
        *,
        stop_requested: Callable[[], bool],
        reason: str,
    ) -> None:
        if seconds <= 0:
            return
        logger.info("Sleeping %s seconds (%s)...", seconds, reason)
        for _ in range(seconds):
            if stop_requested():
                return
            await asyncio.sleep(1.0)
