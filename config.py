import os

# Cấu hình giao diện (UI) - Phong cách "Midnight Zinc" (Chuyên nghiệp / Hiện đại)
WINDOW_TITLE = "Instagram Downloader v6.5 - Midnight UI"
WINDOW_GEOMETRY = "820x920"
COLOR_BG = "#18181B"           # Nền chính (Zinc 900 - Xám đen sâu)
COLOR_TEXT_AREA = "#09090B"    # Nền terminal siêu tối (Zinc 950 - Đen tuyền)
COLOR_PRIMARY = "#EC4899"      # Accent chính: Hồng Pink 500 (Gợi nhớ Instagram)
COLOR_SECONDARY = "#27272A"    # Nền các ô LabelFrame/Input (Zinc 800)
COLOR_SUCCESS = "#10B981"      # Xanh ngọc Emerald 500 (Tươi, rõ ràng)
COLOR_WARNING = "#F59E0B"      # Vàng cam Amber 500 (Cảnh báo/Bắt mắt)
COLOR_LIGHT_BLUE = "#0EA5E9"   # Xanh dương Sky 500 (Tính năng phụ)
COLOR_DANGER = "#EF4444"       # Đỏ Red 500 (Khẩn cấp/Dừng)

# Tham số mặc định
DEFAULT_DOWNLOAD_SUBFOLDER = "instagram"

def get_default_download_path() -> str:
    # Trả về đường dẫn lưu trữ mặc định cố định theo yêu cầu
    return os.path.normpath(r"E:\gallery-dl\instagram")