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
    "429",
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


@dataclass(slots=True)
class RateLimitPolicy:
    min_delay_seconds: int = 18
    max_delay_seconds: int = 45
    batch_size: int = 8
    batch_cooldown_seconds: int = 240
    suspected_limit_cooldown_seconds: int = 900
    jitter_seconds: int = 12
    max_limit_signals_before_stop: int = 2


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
        return any(kw in line.lower() for kw in LIMIT_KEYWORDS)

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
