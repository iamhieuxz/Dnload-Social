from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import utils
from downloader import Downloader
from models import AppConfig, RuntimeState
from rate_limit import RateLimitGuard

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov')

class InstagramService:
    def __init__(
        self,
        downloader: Downloader,
        rate_limit_guard: RateLimitGuard,
        app_config: AppConfig,
        state: RuntimeState,
    ) -> None:
        self.downloader = downloader
        self.rate_limit_guard = rate_limit_guard
        self.app_config = app_config
        self.state = state

    def download_single_new(self, user: str, disable_range: bool) -> None:
        target = self._normalize_instagram_target(user)
        dest_name = self._derive_destination_name(target)
        dest = os.path.join(self.app_config.download_folder, dest_name)
        os.makedirs(dest, exist_ok=True)
        is_single_post = self._is_single_post_target(target)
        
        if is_single_post:
            limit_range = None if disable_range else '1-4'
            disable_range_flag = disable_range
        else:
            limit_range = None
            disable_range_flag = True

        logging.info('➕ Thêm mới tài khoản: @%s', dest_name)
        logging.info('🔍 [LOCAL CHECK]: Kiểm tra toàn bộ dữ liệu trên máy chủ (Sẽ quét tới bài cũ nhất)...')
        has_output = False

        for line in self._download_with_cookie_fallback(
            target, dest, limit_range=limit_range, disable_range=disable_range_flag, source='POST'
        ):
            if self.state.stop_requested: break
            if any(ext in line.lower() for ext in IMAGE_EXTENSIONS):
                has_output = True
                self._log_media_line(line, indent='   ', label='POST')

        if not has_output and not self.state.stop_requested:
            logging.info('   ⏭️ Thư mục profile đã đồng bộ đầy đủ dữ liệu.')
        logging.info('📊 Hoàn tất! Folder đang lưu giữ: %s tệp.', utils.count_local_files(dest))

    def download_list_new(self, disable_range: bool) -> None:
        users = self._read_users_from_list()
        if not users: return

        logging.info('🚀 Phát hiện %s tài khoản trong file danh sách. Bắt đầu quét...', len(users))
        for index, user in enumerate(users, start=1):
            if self.state.stop_requested: break
            if user in self.state.cache_them_moi: continue

            dest = os.path.join(self.app_config.download_folder, user)
            os.makedirs(dest, exist_ok=True)
            logging.info('🌐 [%s/%s] Tài khoản: @%s', index, len(users), user)
            logging.info('   🔍 Đang kết nối máy chủ Instagram & Dò tìm tệp (Quét toàn bộ timeline)...')

            target = self._normalize_instagram_target(user)
            is_single_post = self._is_single_post_target(target)

            limit_range = None if disable_range else '1-4' if is_single_post else None
            disable_range_flag = disable_range if is_single_post else True

            has_output = False
            for line in self._download_with_cookie_fallback(
                target, dest, limit_range=limit_range, disable_range=disable_range_flag, source='POST'
            ):
                if self.state.stop_requested: break
                if any(ext in line.lower() for ext in IMAGE_EXTENSIONS):
                    has_output = True
                    self._log_media_line(line, indent='     ', label='POST')

            if not has_output and not self.state.stop_requested:
                logging.info('     ⏭️ Thư mục đã đồng bộ đầy đủ từ trước.')
            if not self.state.stop_requested:
                self.state.cache_them_moi.add(user)
                self.rate_limit_guard.wait_after_account(stop_requested=lambda: self.state.stop_requested)
        logging.info('🎉 TIẾN TRÌNH QUÉT FILE DANH SÁCH HOÀN THÀNH!')

    def update_single(self, target: str, disable_range: bool, include_posts: bool = True, include_stories: bool = True, include_highlights: bool = False) -> None:
        normalized_target = self._normalize_instagram_target(target)
        dest_name = self._derive_destination_name(normalized_target)
        dest = os.path.join(self.app_config.download_folder, dest_name)
        os.makedirs(dest, exist_ok=True)

        before = utils.count_local_files(dest)
        logging.info('🚀 Kiểm tra tiến trình đồng bộ thông minh cho mục tiêu: %s', normalized_target)
        self._run_layered_sync(
            target=normalized_target,
            dest=dest,
            before_count=before,
            disable_range=disable_range,
            include_posts=include_posts,
            include_stories=include_stories,
            include_highlights=include_highlights,
        )
        after = utils.count_local_files(dest)
        logging.info('📊 Kết quả: Hoàn thành đồng bộ %s. Tăng thêm +%s tệp mới.', normalized_target, after - before)

    def update_list(self, disable_range: bool, include_posts: bool = True, include_stories: bool = True, include_highlights: bool = False) -> None:
        users = self._read_users_from_list()
        if not users: return

        pending_users = [u for u in users if u not in self.state.cache_cap_nhat_nhanh]
        if not pending_users:
            logging.info('⏭️ [CACHE]: Tất cả %s tài khoản trong danh sách đã hoàn tất cập nhật từ trước.', len(users))
            return

        logging.info('🚀 [CẬP NHẬT LIST] Bắt đầu xử lý TUẦN TỰ an toàn cho %s tài khoản...', len(pending_users))

        for index, user in enumerate(pending_users, start=1):
            if self.state.stop_requested: break
            
            normalized_target = self._normalize_instagram_target(user)
            dest_name = self._derive_destination_name(normalized_target)
            dest = os.path.join(self.app_config.download_folder, dest_name)
            os.makedirs(dest, exist_ok=True)

            before = utils.count_local_files(dest)
            logging.info('🔄 [%s/%s] Cập nhật: @%s', index, len(pending_users), dest_name)

            self._run_layered_sync(
                target=normalized_target,
                dest=dest,
                before_count=before,
                disable_range=disable_range,
                include_posts=include_posts,
                include_stories=include_stories,
                include_highlights=include_highlights,
            )

            if not self.state.stop_requested:
                self.state.cache_cap_nhat_nhanh.add(user)
                after = utils.count_local_files(dest)
                if after - before > 0:
                    logging.info('   ✅ @%s: +%s tệp mới (tổng %s).', dest_name, after - before, after)
                else:
                    logging.info('   ⏭️ @%s: giữ nguyên %s tệp.', dest_name, after)
                
                self.rate_limit_guard.wait_after_account(stop_requested=lambda: self.state.stop_requested)

        logging.info('🎉 TIẾN TRÌNH CẬP NHẬT LIST HOÀN THÀNH!')

    def sync_all_local(self) -> None:
        root_path = Path(self.app_config.download_folder)
        subfolders = [p.name for p in root_path.iterdir() if p.is_dir() and not p.name.endswith('._DEAD')]
        logging.info('🚀 Phát hiện %s thư mục dưới local. Kích hoạt càn quét đồng bộ hàng loạt...', len(subfolders))

        for index, folder in enumerate(subfolders, start=1):
            if self.state.stop_requested: break
            if folder in self.state.cache_cap_nhat_all: continue

            dest = os.path.join(self.app_config.download_folder, folder)
            before = utils.count_local_files(dest)
            username = folder.lstrip('@')
            logging.info('\n📥 [%s/%s] Tài khoản IG: @%s', index, len(subfolders), username)

            try:
                self._consume_download(f'https://www.instagram.com/{username}/', dest, limit_range=None, disable_range=True, label='POST', log_new_only=True)
                if not self.state.stop_requested:
                    self._consume_download(f'https://www.instagram.com/stories/{username}/', dest, label='STORY', log_new_only=True)
                if not self.state.stop_requested:
                    self._consume_download(f'https://instagram.com/{username}/highlights', dest, label='HIGHLIGHT', log_new_only=True)
            except Exception:
                logging.exception("⚠️ Bỏ qua tài khoản %s do lỗi cục bộ", username)

            if not self.state.stop_requested:
                self.state.cache_cap_nhat_all.add(folder)
                after = utils.count_local_files(dest)
                if after - before > 0:
                    logging.info('   ✅ Đã đồng bộ thêm +%s file mới.', after - before)
                else:
                    logging.info('   ⏭️ Giữ nguyên %s tệp.', after)
                self.rate_limit_guard.wait_after_account(stop_requested=lambda: self.state.stop_requested)
        logging.info('\n🎉 TIẾN TRÌNH ĐỒNG BỘ ĐỒNG LOẠT INSTAGRAM HOÀN THÀNH!')

    # =========================================================================
    # CÁC HÀM HELPER NỘI BỘ 
    # =========================================================================

    def _read_users_from_list(self) -> list[str]:
        try:
            with open(self.app_config.list_txt_path, 'r', encoding='utf-8') as file:
                return [utils.clean_username(line) for line in file if utils.clean_username(line)]
        except OSError:
            logging.exception('❌ Lỗi: Không thể mở file danh sách.')
            return []

    def _run_layered_sync(self, *, target: str, dest: str, before_count: int, disable_range: bool, include_posts: bool, include_stories: bool, include_highlights: bool) -> None:
        is_single_post = self._is_single_post_target(target)
        
        if include_posts:
            logging.info('📝 Lớp 1: Dò tìm bài đăng (Timeline Feed)...')
            saw_post_media = self._consume_download(
                target, dest, limit_range=None, disable_range=disable_range, label='POST', log_new_only=False
            )
            if not saw_post_media and not self.state.stop_requested:
                logging.warning('⚠️ Không phát hiện media ở lớp POST cho: %s', target)

        if self.state.stop_requested or is_single_post:
            return

        if include_stories:
            logging.info('📸 Lớp 2: Kiểm tra Stories (Tin ngắn 24h)...')
            self._consume_download(self._stories_url(target), dest, label='STORY', log_new_only=False)

        if self.state.stop_requested:
            return

        if include_highlights:
            logging.info('⭐ Lớp 3: Kiểm tra Highlights (Tin nổi bật)...')
            self._consume_download(f'{target.rstrip("/")}/highlights/', dest, label='HIGHLIGHT', log_new_only=False)

    def _consume_download(self, url: str, dest: str, *, limit_range: str | None = None, disable_range: bool = False, label: str, log_new_only: bool) -> bool:
        saw_media = False
        saw_meaningful_output = False
        
        # [CẤU HÌNH MỚI] Ấn định Tiền tố phụ thuộc vào Lớp quét
        prefix = ""
        if label == 'STORY':
            prefix = "STORY_"
        elif label == 'HIGHLIGHT':
            prefix = "HL_"

        for line in self._download_with_cookie_fallback(url, dest, limit_range=limit_range, disable_range=disable_range, source=label, prefix=prefix):
            if self.state.stop_requested: break
            stripped = line.strip()
            lower = stripped.lower()
            if not stripped: continue

            # 1. Bắt Rate Limit (429)
            if self.rate_limit_guard.detect_limit_signal(stripped):
                saw_meaningful_output = True
                should_stop = self.rate_limit_guard.record_limit_signal(label)
                if should_stop:
                    logging.warning('🛑 Tạm dừng tác vụ để bảo vệ cookie/tài khoản. Hãy thử lại sau.')
                    self.state.stop_requested = True
                    self.downloader.pm.stop()
                    break
                self.rate_limit_guard.wait_after_limit_signal(stop_requested=lambda: self.state.stop_requested)
                continue

            # 2. Lỗi Cookie bị từ chối / Bắt đăng nhập (Mã 4)
            if 'http redirect to home page' in lower or 'login required' in lower:
                saw_meaningful_output = True
                logging.warning('⚠️ [%s] Cookie bị từ chối quyền truy cập (Mã lỗi 4).', label)
                continue

            # 3. Lỗi Rớt mạng vật lý
            if any(token in lower for token in ('time out', 'timeout', 'connection reset', 'network unreachable', '10054')):
                saw_meaningful_output = True
                logging.warning('⚠️ [%s] Lỗi kết nối mạng: %s', label, stripped)
                continue

            # 4. Các lỗi chung khác của gallery-dl
            if any(token in lower for token in ('[error]', 'error:', 'exception', 'failed', '404 not found', 'permission')):
                saw_meaningful_output = True
                logging.warning('⚠️ [%s] %s', label, stripped)
                continue

            if not any(ext in lower for ext in IMAGE_EXTENSIONS): continue

            saw_media = True
            saw_meaningful_output = True
            
            is_new = not stripped.startswith('#')
            clean_path = stripped.lstrip('#').strip()

            if log_new_only and not is_new: continue

            if is_new:
                logging.info('   [NEW %s] -> %s', label, os.path.basename(clean_path))
            else:
                logging.info('   [ĐÃ CÓ %s] • %s', label, os.path.basename(clean_path))

        if not saw_media and not saw_meaningful_output and not self.state.stop_requested:
            logging.warning('⚠️ [%s] Không nhận được dữ liệu từ gallery-dl. Hãy kiểm tra cookie, link.', label)
        return saw_media

    def _download_with_cookie_fallback(
        self,
        url: str,
        dest: str,
        *,
        limit_range: str | None,
        disable_range: bool,
        source: str,
        prefix: str = "", # [THÊM MỚI]
    ) -> Any:
        
        cookie_paths = [self.app_config.cookie_path]
        if self.app_config.backup_cookie_path and self.app_config.backup_cookie_path != self.app_config.cookie_path:
            cookie_paths.append(self.app_config.backup_cookie_path)

        for index, cookie_path in enumerate(cookie_paths, start=1):
            saw_limit = False
            for line in self.downloader.execute_download(url, dest, cookie_path, limit_range, disable_range=disable_range, prefix=prefix):
                if self.rate_limit_guard.detect_limit_signal(line):
                    saw_limit = True
                yield line
                if self.state.stop_requested: return
            if not saw_limit: return
            
            logging.warning('⚠️ Cookie %s có dấu hiệu bị giới hạn ở %s.', index, source)
            if index < len(cookie_paths) and not self.state.stop_requested:
                logging.warning('⚠️ Thử lại bằng cookie dự phòng...')
                self.rate_limit_guard.wait_after_limit_signal(stop_requested=lambda: self.state.stop_requested)

    def _log_media_line(self, line: str, *, indent: str, label: str) -> None:
        stripped = line.strip()
        lower = stripped.lower()
        if not any(ext in lower for ext in IMAGE_EXTENSIONS): return
        
        is_new = not stripped.startswith('#')
        clean_path = stripped.lstrip('#').strip()
        
        if is_new:
            logging.info('%s[NEW %s] -> %s', indent, label, os.path.basename(clean_path))
        else:
            logging.info('%s[ĐÃ CÓ %s] • %s', indent, label, os.path.basename(clean_path))

    def _normalize_instagram_target(self, target: str) -> str:
        cleaned = target.strip().replace('https://www.instagram.com/', '').replace('https://instagram.com/', '')
        cleaned = cleaned.split('?')[0].split('#')[0].strip('/')
        if cleaned.startswith('http://') or cleaned.startswith('https://'):
            return cleaned.rstrip('/') + '/'
        return f'https://www.instagram.com/{cleaned}/'

    def _is_single_post_target(self, target: str) -> bool:
        path = target.replace('https://www.instagram.com/', '').replace('https://instagram.com/', '').strip('/')
        return path.startswith(('p/', 'reel/', 'reels/', 'tv/')) or any(marker in path for marker in ('/p/', '/reel/', '/reels/', '/tv/'))

    def _derive_destination_name(self, target: str) -> str:
        parts = [part for part in target.rstrip('/').split('/') if part]
        if not parts: return 'instagram'
        if parts[-1] in {'stories', 'highlights'} and len(parts) >= 2:
            candidate = parts[-2]
        elif len(parts) >= 2 and parts[-2] == 'stories':
            candidate = parts[-1]
        else:
            candidate = parts[-1]
        return utils.clean_username(candidate) or 'instagram'

    def _stories_url(self, target: str) -> str:
        username = self._derive_destination_name(self._normalize_instagram_target(target))
        return f'https://www.instagram.com/stories/{username}/'