from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass


LIMIT_KEYWORDS = (
    '429',
    'too many requests',
    'rate limit',
    'ratelimit',
    'please wait a few minutes',
    'temporarily blocked',
    'try again later',
    'login required',
    'checkpoint',
    'challenge required',
    'feedback_required',
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
        lower_line = line.lower()
        return any(keyword in lower_line for keyword in LIMIT_KEYWORDS)

    def record_limit_signal(self, source: str) -> bool:
        self._limit_signals += 1
        logging.warning(
            '⚠️ Phát hiện dấu hiệu bị giới hạn từ %s (%s/%s).',
            source,
            self._limit_signals,
            self.policy.max_limit_signals_before_stop,
        )
        return self._limit_signals >= self.policy.max_limit_signals_before_stop

    def wait_after_account(self, *, stop_requested: callable) -> None:
        self._processed_count += 1
        if self._processed_count % self.policy.batch_size == 0:
            self._sleep_interruptibly(
                self.policy.batch_cooldown_seconds,
                stop_requested=stop_requested,
                reason='nghỉ batch để giảm rủi ro bị limit',
            )
            return

        delay = random.randint(self.policy.min_delay_seconds, self.policy.max_delay_seconds)
        delay += random.randint(0, self.policy.jitter_seconds)
        self._sleep_interruptibly(delay, stop_requested=stop_requested, reason='giãn nhịp request')

    def wait_after_limit_signal(self, *, stop_requested: callable) -> None:
        self._sleep_interruptibly(
            self.policy.suspected_limit_cooldown_seconds,
            stop_requested=stop_requested,
            reason='nghỉ do nghi ngờ bị limit',
        )

    def _sleep_interruptibly(self, seconds: int, *, stop_requested: callable, reason: str) -> None:
        if seconds <= 0:
            return
        logging.info('⏳ Tạm nghỉ %s giây (%s)...', seconds, reason)
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if stop_requested():
                return
            time.sleep(min(1.0, end_time - time.monotonic()))
