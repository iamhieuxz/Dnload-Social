from __future__ import annotations

import tkinter as tk

import config
import utils
from downloader import Downloader
from gui import IGToolGUI
from models import AppConfig, RuntimeState
from process_manager import ProcessManager
from rate_limit import RateLimitGuard, RateLimitPolicy
from services import InstagramService


def main() -> None:
    # 0. Dọn dẹp rác hệ thống từ các phiên bản bị crash trước đó
    utils.cleanup_temp_cookies()

    # 1. Khởi tạo Trạng thái & Cấu hình (Models / State)
    app_config = AppConfig(download_folder=config.get_default_download_path())
    state = RuntimeState()

    # 2. Khởi tạo các thành phần Hạ tầng (Infrastructure)
    pm = ProcessManager()
    downloader = Downloader(pm)
    rate_limit_guard = RateLimitGuard(RateLimitPolicy())

    # 3. Khởi tạo tầng Xử lý nghiệp vụ (Business Logic / Service)
    service = InstagramService(downloader, rate_limit_guard, app_config, state)

    # 4. Khởi tạo Giao diện (UI / View)
    root = tk.Tk()
    # Tiêm (Inject) các dependencies vào GUI
    IGToolGUI(root, app_config, state, pm, service)
    
    # Chạy vòng lặp giao diện
    root.mainloop()


if __name__ == '__main__':
    main()