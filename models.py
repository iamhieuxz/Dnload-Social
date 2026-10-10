from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Set


@dataclass(slots=True)
class AppConfig:
    download_folder: str
    cookie_path: str = ""
    backup_cookie_path: str = ""
    list_txt_path: str = ""

    def normalized_download_folder(self) -> str:
        return str(Path(self.download_folder).expanduser().resolve())


@dataclass(slots=True)
class RuntimeState:
    is_tool_unlocked: bool = False
    stop_requested: bool = False
    cache_them_moi: Set[str] = field(default_factory=set)
    cache_cap_nhat_all: Set[str] = field(default_factory=set)
    # [TÍNH NĂNG MỚI] Cache lưu tiến trình của Nút 2 (Cập nhật nhanh List)
    cache_cap_nhat_nhanh: Set[str] = field(default_factory=set)