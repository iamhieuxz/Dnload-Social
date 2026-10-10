from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rate_limit import RateLimitPolicy


REQUESTS_PER_ACCOUNT_UPDATE_ALL = 3


@dataclass(slots=True)
class LimitEstimate:
    account_count: int
    estimated_requests: int
    minimum_seconds: int
    maximum_seconds: int
    batch_cooldowns: int
    risk_level: str


def estimate_update_all(download_folder: str, policy: RateLimitPolicy | None = None) -> LimitEstimate:
    policy = policy or RateLimitPolicy()
    root = Path(download_folder)
    account_count = 0
    if root.exists():
        account_count = sum(1 for child in root.iterdir() if child.is_dir() and not child.name.endswith('._DEAD'))

    estimated_requests = account_count * REQUESTS_PER_ACCOUNT_UPDATE_ALL
    batch_cooldowns = account_count // policy.batch_size
    minimum_seconds = account_count * policy.min_delay_seconds + batch_cooldowns * policy.batch_cooldown_seconds
    maximum_seconds = account_count * (policy.max_delay_seconds + policy.jitter_seconds) + batch_cooldowns * policy.batch_cooldown_seconds

    if estimated_requests >= 250 or account_count >= 80:
        risk_level = 'cao'
    elif estimated_requests >= 90 or account_count >= 30:
        risk_level = 'trung bình'
    else:
        risk_level = 'thấp'

    return LimitEstimate(
        account_count=account_count,
        estimated_requests=estimated_requests,
        minimum_seconds=minimum_seconds,
        maximum_seconds=maximum_seconds,
        batch_cooldowns=batch_cooldowns,
        risk_level=risk_level,
    )


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f'{hours}h {minute}m {sec}s'
    return f'{minute}m {sec}s'


if __name__ == '__main__':
    folder = r'E:\gallery-dl\instagram'
    estimate = estimate_update_all(folder)
    print(f'Folder: {folder}')
    print(f'Số thư mục account: {estimate.account_count}')
    print(f'Ước tính request update-all: {estimate.estimated_requests}')
    print(f'Số lần nghỉ batch: {estimate.batch_cooldowns}')
    print(f'Thời gian an toàn ước tính: {format_duration(estimate.minimum_seconds)} - {format_duration(estimate.maximum_seconds)}')
    print(f'Mức rủi ro bị limit: {estimate.risk_level}')
