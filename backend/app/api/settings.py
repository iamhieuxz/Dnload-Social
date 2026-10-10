from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings_endpoint() -> SettingsOut:
    s = get_settings()
    cookie_dir = s.get_cookie_folder()
    has_cookies = any(cookie_dir.glob("cookie*.txt")) if cookie_dir.exists() else False
    return SettingsOut(
        download_folder=s.download_folder,
        cookie_folder=s.cookie_folder,
        rate_limit_min_delay=s.rate_limit_min_delay,
        rate_limit_max_delay=s.rate_limit_max_delay,
        rate_limit_batch_size=s.rate_limit_batch_size,
        rate_limit_batch_cooldown=s.rate_limit_batch_cooldown,
        rate_limit_limit_cooldown=s.rate_limit_limit_cooldown,
        rate_limit_max_signals=s.rate_limit_max_signals,
        cookies_configured=has_cookies,
    )


@router.patch("", response_model=SettingsOut)
async def update_settings_endpoint(payload: SettingsUpdate) -> SettingsOut:
    """
    Note: most rate-limit / folder settings come from env vars and require
    a server restart. This endpoint exists so the UI can save into the
    settings table for future extensibility (cookie uploads, etc.).
    """
    # Currently we just echo the current settings.
    return await get_settings_endpoint()
