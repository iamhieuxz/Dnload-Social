from __future__ import annotations

import logging
import os
import queue
import threading
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox

import config
import utils
from models import AppConfig, RuntimeState
from process_manager import ProcessManager
from services import InstagramService

QUEUE_POLL_MS = 50
FONT_MAIN = ('Segoe UI', 9)
FONT_BOLD = ('Segoe UI', 9, 'bold')
FONT_ITALIC = ('Segoe UI', 9, 'italic')
FONT_TITLE = ('Segoe UI', 15, 'bold')
FONT_FRAME_TITLE = ('Segoe UI', 10, 'bold')

# Màu chữ tiêu chuẩn cho theme tối
TEXT_MAIN = "#F4F4F5"  # Zinc 100
TEXT_MUTED = "#A1A1AA" # Zinc 400


@dataclass(slots=True)
class LogEvent:
    message: str
    tag: str


class CustomColorTextHandler(logging.Handler):
    def __init__(self, ui_queue: "queue.Queue[tuple[str, Any]]") -> None:
        super().__init__()
        self.ui_queue = ui_queue

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record).rstrip('\n')
        self.ui_queue.put(("log", LogEvent(message=message, tag=self._tag_for(message))))

    def _tag_for(self, message: str) -> str:
        if any(token in message for token in ('↳ Kết quả:', '⏭️', 'Giữ nguyên', '[ĐÃ CÓ]', '•')):
            return 'FILE_OLD'
        if any(token in message for token in ('-> ', 'file mới', '✅', '[TẢI MỚI]', '[NEW', '[DL]')):
            return 'FILE_NEW'
        if any(icon in message for icon in ("[ENGINE]", "➕", "🚀", "🔄", "🎉", "🔍", "🌐")):
            return 'LOG_SYSTEM'
        if any(icon in message for icon in ('⚠️', '⏳', '🛑', '🔒')):
            return 'LOG_WARN'
        return 'LOG_NORMAL'


class IGToolGUI:
    def __init__(
        self,
        root: tk.Tk,
        app_config: AppConfig,
        state: RuntimeState,
        pm: ProcessManager,
        service: InstagramService,
    ) -> None:
        self.root = root
        self.root.title(config.WINDOW_TITLE)
        self.root.geometry(config.WINDOW_GEOMETRY)
        self.root.resizable(False, False)
        self.root.configure(bg=config.COLOR_BG)

        self.app_config = app_config
        self.state = state
        self.pm = pm
        self.service = service

        self.ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='igdl')
        self._log_handler: CustomColorTextHandler | None = None
        self._shutdown_lock = threading.Lock()
        self._active_future: Future[Any] | None = None

        self.mode_them_moi = tk.StringVar(value='single')
        self.disable_range_var = tk.BooleanVar(value=True)
        
        self.chk_post_var = tk.BooleanVar(value=True)
        self.chk_story_var = tk.BooleanVar(value=True)
        self.chk_highlight_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._setup_logging()
        self.process_ui_queue()
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

        logging.warning('🔒 HỆ THỐNG ĐANG KHÓA. Hãy nạp ít nhất Cookie 1 (Chính) để kích hoạt tool.')

    def _build_ui(self) -> None:
        self._title_label = tk.Label(
            self.root,
            text='INSTAGRAM DOWNLOADER v6.5 (MIDNIGHT ARCHITECTURE)',
            font=FONT_TITLE,
            fg=config.COLOR_PRIMARY,
            bg=config.COLOR_BG,
        )
        self._title_label.pack(pady=(15, 5))

        self._build_cookie_section()
        self._build_folder_section()
        self._build_input_section()
        self._build_control_section()
        self._build_log_section()

    def _build_cookie_section(self) -> None:
        frame_cookie = tk.LabelFrame(self.root, text=" ⚙️ BƯỚC 1: Cấu hình hệ thống Cookie Instagram ", font=FONT_FRAME_TITLE, fg=config.COLOR_WARNING, bg=config.COLOR_BG, bd=1, highlightbackground=config.COLOR_SECONDARY)
        frame_cookie.pack(pady=8, fill='x', padx=20, ipadx=5, ipady=5)

        frame_c1 = tk.Frame(frame_cookie, bg=config.COLOR_BG)
        frame_c1.pack(fill='x', padx=10, pady=4)
        self.lbl_c1 = tk.Label(frame_c1, text='🔑 Chưa nạp Cookie Instagram 1 (Chính - Bắt buộc)...', font=FONT_ITALIC, bg=config.COLOR_SECONDARY, fg=config.COLOR_WARNING, anchor='w', bd=0, height=2, padx=10)
        self.lbl_c1.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.btn_c1 = tk.Button(frame_c1, text='📁 Chọn Cookie 1', font=FONT_BOLD, bg=config.COLOR_WARNING, fg='#000000', bd=0, cursor='hand2', width=15, activebackground='#FBBF24', command=self.load_cookie_1)
        self.btn_c1.pack(side='right', ipady=4)

        frame_c2 = tk.Frame(frame_cookie, bg=config.COLOR_BG)
        frame_c2.pack(fill='x', padx=10, pady=4)
        self.lbl_c2 = tk.Label(frame_c2, text='🛡️ Chưa nạp Cookie Instagram 2 (Tùy chọn phụ)...', font=FONT_ITALIC, bg=config.COLOR_SECONDARY, fg=TEXT_MUTED, anchor='w', bd=0, height=2, padx=10)
        self.lbl_c2.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.btn_c2 = tk.Button(frame_c2, text='📁 Chọn Cookie 2', font=FONT_BOLD, bg=config.COLOR_LIGHT_BLUE, fg='#000000', bd=0, cursor='hand2', width=15, activebackground='#38BDF8', command=self.load_cookie_2)
        self.btn_c2.pack(side='right', ipady=4)

        tk.Button(frame_cookie, text='💡 Bấm vào đây để cài Extension xuất file Get-Cookies.txt chuẩn xác', font=FONT_BOLD, bg=config.COLOR_SECONDARY, fg=config.COLOR_PRIMARY, bd=0, cursor='hand2', activebackground=config.COLOR_BG, activeforeground=config.COLOR_PRIMARY, command=lambda: webbrowser.open('https://chromewebstore.google.com/detail/get-cookiestxt-locally/ccoliddmhmocdefkdbehicnelgbelmpe')).pack(fill='x', padx=10, pady=(6, 2), ipady=4)

    def _build_folder_section(self) -> None:
        frame_folder = tk.LabelFrame(self.root, text=" 📂 BƯỚC 2: Đường dẫn thư mục lưu trữ ", font=FONT_FRAME_TITLE, fg=config.COLOR_LIGHT_BLUE, bg=config.COLOR_BG, bd=1, highlightbackground=config.COLOR_SECONDARY)
        frame_folder.pack(pady=8, fill='x', padx=20, ipadx=5, ipady=5)

        row = tk.Frame(frame_folder, bg=config.COLOR_BG)
        row.pack(fill='x', padx=10, pady=2)
        self.lbl_display_folder = tk.Label(row, text=self.app_config.download_folder, font=FONT_BOLD, bg=config.COLOR_SECONDARY, fg=config.COLOR_PRIMARY, anchor='w', bd=0, height=2, padx=10)
        self.lbl_display_folder.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.btn_folder = tk.Button(row, text='⚙️ Đổi Thư Mục', font=FONT_BOLD, bg=config.COLOR_LIGHT_BLUE, fg='#000000', bd=0, cursor='hand2', width=15, activebackground='#38BDF8', command=self.change_folder)
        self.btn_folder.pack(side='right', ipady=4)

    def _build_input_section(self) -> None:
        frame_input = tk.LabelFrame(self.root, text=" 🎯 BƯỚC 3: Mục tiêu tải xuống ", font=FONT_FRAME_TITLE, fg=config.COLOR_SUCCESS, bg=config.COLOR_BG, bd=1, highlightbackground=config.COLOR_SECONDARY)
        frame_input.pack(pady=8, fill='x', padx=20, ipadx=5, ipady=5)

        frame_radio = tk.Frame(frame_input, bg=config.COLOR_BG)
        frame_radio.pack(fill='x', padx=10, pady=4)
        tk.Radiobutton(frame_radio, text='Chế độ 1: 1 Profile / Link', variable=self.mode_them_moi, value='single', bg=config.COLOR_BG, fg=TEXT_MAIN, selectcolor=config.COLOR_SECONDARY, activebackground=config.COLOR_BG, activeforeground=TEXT_MAIN, font=FONT_BOLD, command=self.toggle_mode).pack(side='left', padx=(0, 30))
        tk.Radiobutton(frame_radio, text='Chế độ 2: File List (.txt)', variable=self.mode_them_moi, value='list', bg=config.COLOR_BG, fg=TEXT_MAIN, selectcolor=config.COLOR_SECONDARY, activebackground=config.COLOR_BG, activeforeground=TEXT_MAIN, font=FONT_BOLD, command=self.toggle_mode).pack(side='left')

        self.entry_link = tk.Entry(frame_input, font=('Segoe UI', 11), bg=config.COLOR_SECONDARY, fg=TEXT_MAIN, insertbackground=TEXT_MAIN, bd=0)
        self.entry_link.pack(fill='x', padx=10, pady=4, ipady=6)

        row = tk.Frame(frame_input, bg=config.COLOR_BG)
        row.pack(fill='x', padx=10, pady=4)
        self.lbl_list_txt = tk.Label(row, text='Chưa chọn file danh sách tài khoản .txt...', font=FONT_ITALIC, bg=config.COLOR_SECONDARY, fg=TEXT_MUTED, anchor='w', bd=0, height=2, padx=10)
        self.lbl_list_txt.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.btn_browse_list = tk.Button(row, text='📁 Chọn File List', font=FONT_BOLD, bg=config.COLOR_SUCCESS, fg='#000000', bd=0, cursor='hand2', width=15, activebackground='#34D399', command=self.load_list_txt, state=tk.DISABLED)
        self.btn_browse_list.pack(side='right', ipady=4)

        frame_layers = tk.Frame(frame_input, bg=config.COLOR_BG)
        frame_layers.pack(fill='x', padx=10, pady=(6, 0))
        tk.Label(frame_layers, text='Lớp quét (Cho Nút 2):', font=FONT_BOLD, fg=config.COLOR_WARNING, bg=config.COLOR_BG).pack(side='left', padx=(0, 5))
        
        self.chk_post = tk.Checkbutton(frame_layers, text='Post', variable=self.chk_post_var, bg=config.COLOR_BG, fg=TEXT_MAIN, selectcolor=config.COLOR_SECONDARY, activebackground=config.COLOR_BG, activeforeground=TEXT_MAIN, font=FONT_MAIN)
        self.chk_post.pack(side='left', padx=5)
        
        self.chk_story = tk.Checkbutton(frame_layers, text='Story', variable=self.chk_story_var, bg=config.COLOR_BG, fg=TEXT_MAIN, selectcolor=config.COLOR_SECONDARY, activebackground=config.COLOR_BG, activeforeground=TEXT_MAIN, font=FONT_MAIN)
        self.chk_story.pack(side='left', padx=5)
        
        self.chk_highlight = tk.Checkbutton(frame_layers, text='Highlight', variable=self.chk_highlight_var, bg=config.COLOR_BG, fg=TEXT_MAIN, selectcolor=config.COLOR_SECONDARY, activebackground=config.COLOR_BG, activeforeground=TEXT_MAIN, font=FONT_MAIN)
        self.chk_highlight.pack(side='left', padx=5)

        self.chk_disable_range = tk.Checkbutton(frame_input, text='Tắt giới hạn range để tải đủ mọi media của bài post', variable=self.disable_range_var, onvalue=True, offvalue=False, bg=config.COLOR_BG, fg=TEXT_MAIN, selectcolor=config.COLOR_SECONDARY, activebackground=config.COLOR_BG, activeforeground=TEXT_MAIN, font=FONT_BOLD, command=self._on_disable_range_toggle)
        self.chk_disable_range.pack(anchor='w', padx=10, pady=(4, 4))

    def _build_control_section(self) -> None:
        frame = tk.Frame(self.root, bg=config.COLOR_BG)
        frame.pack(pady=10)
        self.btn1 = tk.Button(frame, text='[1] THÊM MỚI\n(Theo cấu hình B3)', font=FONT_BOLD, fg='#000000', bg=config.COLOR_WARNING, activebackground='#FBBF24', state=tk.DISABLED, width=20, height=2, bd=0, cursor='hand2', command=self.handle_btn1)
        self.btn1.grid(row=0, column=0, padx=6, pady=5)
        self.btn2 = tk.Button(frame, text='[2] CẬP NHẬT NHANH\n(1 mục tiêu hoặc List)', font=FONT_BOLD, fg='#000000', bg=config.COLOR_SUCCESS, activebackground='#34D399', state=tk.DISABLED, width=22, height=2, bd=0, cursor='hand2', command=self.handle_btn2)
        self.btn2.grid(row=0, column=1, padx=6, pady=5)
        self.btn3 = tk.Button(frame, text='[3] CẬP NHẬT TOÀN BỘ\n(Dò quét local)', font=FONT_BOLD, fg='#000000', bg=config.COLOR_LIGHT_BLUE, activebackground='#38BDF8', state=tk.DISABLED, width=20, height=2, bd=0, cursor='hand2', command=self.handle_btn3)
        self.btn3.grid(row=0, column=2, padx=6, pady=5)
        self.btn_stop = tk.Button(frame, text='\n[STOP] DỪNG LẠI', font=FONT_BOLD, fg='#FFFFFF', bg=config.COLOR_DANGER, activebackground='#F87171', state=tk.DISABLED, width=15, height=2, bd=0, cursor='hand2', command=self.handle_stop)
        self.btn_stop.grid(row=0, column=3, padx=6, pady=5)

    def _build_log_section(self) -> None:
        tk.Label(self.root, text='Tiến trình chạy ngầm & Trạng thái Engine:', font=FONT_FRAME_TITLE, fg=TEXT_MUTED, bg=config.COLOR_BG).pack(anchor='w', padx=20, pady=(5,0))
        
        log_frame = tk.Frame(self.root, bg=config.COLOR_SECONDARY, bd=1)
        log_frame.pack(fill='both', expand=True, padx=20, pady=(5, 15))

        self.txt_log = tk.Text(log_frame, bg=config.COLOR_TEXT_AREA, fg=TEXT_MAIN, font=('Consolas', 10), bd=0, padx=10, pady=10)
        self.txt_log.pack(fill='both', expand=True, padx=1, pady=1)
        
        self.txt_log.tag_config('LOG_SYSTEM', foreground=config.COLOR_LIGHT_BLUE)
        self.txt_log.tag_config('LOG_WARN', foreground=config.COLOR_WARNING)
        self.txt_log.tag_config('FILE_OLD', foreground='#52525B') # Màu xám mờ Zinc 600 cho file cũ
        self.txt_log.tag_config('FILE_NEW', foreground=config.COLOR_SUCCESS)
        self.txt_log.tag_config('LOG_NORMAL', foreground=TEXT_MAIN)

    def _setup_logging(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        if self._log_handler is not None:
            logger.removeHandler(self._log_handler)
        handler = CustomColorTextHandler(self.ui_queue)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        self._log_handler = handler

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.set_buttons_state(state)
        self.btn_stop.config(state=tk.NORMAL if busy else tk.DISABLED)
        if not busy:
            self.toggle_mode()
            self._sync_range_checkbox_state()

    def set_buttons_state(self, state: str) -> None:
        widgets_to_toggle = (
            self.btn1, self.btn2, self.btn3, 
            self.btn_c1, self.btn_c2, self.btn_folder,
            self.chk_post, self.chk_story, self.chk_highlight
        )
        for widget in widgets_to_toggle:
            widget.config(state=state)

    def load_cookie_1(self) -> None:
        path = filedialog.askopenfilename(title='Chọn file chứa Instagram Cookie 1 (Chính)', filetypes=[('Text Files', '*.txt')])
        if not path: return
        self.app_config.cookie_path = path
        self.lbl_c1.config(text=f' ✔ C1: {os.path.basename(path)}', fg=config.COLOR_SUCCESS)
        self.state.is_tool_unlocked = True
        self.set_buttons_state(tk.NORMAL)
        self.toggle_mode()
        logging.info('🔓 ĐÃ NẠP COOKIE CHÍNH INSTAGRAM: Hệ thống đã mở khóa hoàn toàn.')

    def load_cookie_2(self) -> None:
        path = filedialog.askopenfilename(title='Chọn file chứa Instagram Cookie 2 (Phụ)', filetypes=[('Text Files', '*.txt')])
        if not path: return
        self.app_config.backup_cookie_path = path
        self.lbl_c2.config(text=f' ✔ C2 (Dự phòng): {os.path.basename(path)}', fg=config.COLOR_LIGHT_BLUE)
        logging.info('🛡️ ĐÃ NẠP COOKIE PHỤ INSTAGRAM: Sẵn sàng hỗ trợ vận hành.')

    def change_folder(self) -> None:
        folder = filedialog.askdirectory(title='Chọn thư mục chứa ảnh/video Instagram')
        if not folder: return
        self.app_config.download_folder = os.path.normpath(folder)
        self.lbl_display_folder.config(text=self.app_config.download_folder)
        logging.info('⚙️ Thư mục lưu trữ đã thay đổi sang: %s', self.app_config.download_folder)

    def load_list_txt(self) -> None:
        path = filedialog.askopenfilename(title='Chọn file danh sách tài khoản IG (.txt)', filetypes=[('Text Files', '*.txt')])
        if not path: return
        self.app_config.list_txt_path = path
        self.lbl_list_txt.config(text=f' 📋 {os.path.basename(path)}', fg=config.COLOR_LIGHT_BLUE)
        self.state.cache_them_moi.clear()
        self.state.cache_cap_nhat_nhanh.clear()
        logging.info('🧠 [CACHE]: Đã làm sạch bộ nhớ tạm do danh sách tệp đầu vào vừa cập nhật.')

    def toggle_mode(self) -> None:
        if self.mode_them_moi.get() == 'single':
            self.entry_link.config(state=tk.NORMAL, bg=config.COLOR_SECONDARY)
            self.btn_browse_list.config(state=tk.DISABLED)
        else:
            self.entry_link.config(state=tk.DISABLED, bg=config.COLOR_BG)
            self.btn_browse_list.config(state=tk.NORMAL if self.state.is_tool_unlocked else tk.DISABLED)
        self._sync_range_checkbox_state()

    def _sync_range_checkbox_state(self) -> None:
        if self.mode_them_moi.get() == 'single':
            self.chk_disable_range.config(state=tk.NORMAL)
        else:
            self.chk_disable_range.config(state=tk.DISABLED)
            self.disable_range_var.set(True)

    def _on_disable_range_toggle(self) -> None:
        logging.info('⚙️ Chế độ tải đầy đủ media của post: %s', 'BẬT' if self.disable_range_var.get() else 'TẮT')

    def _submit_job(self, target: Callable[[], None]) -> None:
        self.state.stop_requested = False
        self._set_busy(True)
        self._active_future = self.executor.submit(self._safe_job_wrapper, target)

    def _safe_job_wrapper(self, target: Callable[[], None]) -> None:
        try:
            target()
        except Exception:
            logging.exception('Lỗi không xử lý được trong tiến trình nền')
        finally:
            self.ui_queue.put(('reset_ui', None))

    def handle_btn1(self) -> None:
        disable_range = self.disable_range_var.get()
        if self.mode_them_moi.get() == 'single':
            user = utils.clean_username(self.entry_link.get())
            if not user:
                messagebox.showwarning('Thiếu thông tin', 'Vui lòng nhập chính xác Username Instagram cần quét!')
                return
            self._submit_job(lambda: self.service.download_single_new(user, disable_range))
        else:
            if not self.app_config.list_txt_path or not os.path.exists(self.app_config.list_txt_path):
                messagebox.showwarning('Thiếu thông tin', 'Vui lòng chọn file danh sách tài khoản .txt ở Bước 3 trước!')
                return
            self._submit_job(lambda: self.service.download_list_new(disable_range))

    def handle_btn2(self) -> None:
        disable_range = self.disable_range_var.get()
        inc_post = self.chk_post_var.get()
        inc_story = self.chk_story_var.get()
        inc_high = self.chk_highlight_var.get()
        
        if not (inc_post or inc_story or inc_high):
            messagebox.showwarning("Lỗi Tùy Chọn", "Bạn phải chọn ít nhất 1 lớp dữ liệu (Post, Story hoặc Highlight) để cập nhật!")
            return

        if self.mode_them_moi.get() == 'list':
            if not self.app_config.list_txt_path or not os.path.exists(self.app_config.list_txt_path):
                messagebox.showwarning('Thiếu thông tin', 'Vui lòng chọn file danh sách tài khoản .txt ở Bước 3 trước!')
                return
            self._submit_job(lambda: self.service.update_list(disable_range, inc_post, inc_story, inc_high))
            return

        target = self.entry_link.get().strip()
        if not target:
            messagebox.showwarning('Thiếu thông tin', 'Nhập Username hoặc link Instagram để quét nhanh cập nhật!')
            return
        self._submit_job(lambda: self.service.update_single(target, disable_range, inc_post, inc_story, inc_high))

    def handle_btn3(self) -> None:
        if not os.path.exists(self.app_config.download_folder):
            messagebox.showwarning('Lỗi', 'Thư mục local rỗng hoặc chưa từng tải dữ liệu nào về.')
            return
        self._submit_job(self.service.sync_all_local)

    def handle_stop(self) -> None:
        if not messagebox.askyesno('Xác nhận', 'Bạn có muốn DỪNG TIẾN TRÌNH hiện tại?'):
            return
        self.state.stop_requested = True
        self.pm.stop()
        logging.warning('\n⏹️ ĐÃ CƯỠNG CHẾ TẮT CÁC ENGINE THEO YÊU CẦU.')
        self.ui_queue.put(('reset_ui', None))

    def process_ui_queue(self) -> None:
        try:
            while True:
                action, data = self.ui_queue.get_nowait()
                if action == 'log' and isinstance(data, LogEvent):
                    if self._should_filter_log(data.message):
                        continue
                    self.txt_log.insert(tk.END, data.message + '\n', data.tag)
                    self.txt_log.see(tk.END)
                elif action == 'reset_ui':
                    self._set_busy(False)
                self.ui_queue.task_done()
        except queue.Empty:
            pass
        self.root.after(QUEUE_POLL_MS, self.process_ui_queue)

    def _should_filter_log(self, message: str) -> bool:
        """Filter noise lines; keep only what the user needs to see."""
        if not message.strip():
            return True

        # Bỏ dòng lệnh gallery-dl đầy đủ
        if message.startswith('[gallery-dl'):
            return True

        # Bỏ archive path — sqlite internal, không cần
        if 'download_archive' in message or '.sqlite' in message:
            return True

        # Bỏ URL health check của chính gallery-dl
        if message.startswith('http:'):
            return True

        # Bỏ media list header (chỉ giữ dòng file cụ thể)
        stripped = message.strip()
        if stripped.startswith('[') and ':' in stripped and 'http' in stripped:
            return True

        return False

    def on_close(self) -> None:
        self.shutdown()
        self.root.destroy()

    def shutdown(self) -> None:
        with self._shutdown_lock:
            self.state.stop_requested = True
            self.pm.stop()
            self.executor.shutdown(wait=False, cancel_futures=True)
            if self._log_handler is not None:
                logging.getLogger().removeHandler(self._log_handler)
                self._log_handler = None