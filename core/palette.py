"""
Color palette for file types (used in storage analytics UI).
Mỗi loại file (theo phần mở rộng) một màu riêng.
"""
import os

# Bảng màu theo phần mở rộng
EXT_COLORS = {
    # Documents
    "pdf": "#e74c3c",
    "doc": "#2b5797",
    "docx": "#2b5797",
    "ppt": "#d24726",
    "pptx": "#d24726",
    "xls": "#217346",
    "xlsx": "#217346",
    "txt": "#7f8c8d",
    "md": "#34495e",
    "rtf": "#95a5a6",
    "csv": "#16a085",
    # Images
    "jpg": "#f39c12",
    "jpeg": "#f39c12",
    "png": "#e67e22",
    "gif": "#9b59b6",
    "webp": "#d35400",
    "bmp": "#c0392b",
    "svg": "#8e44ad",
    "ico": "#6c3483",
    "heic": "#a04000",
    # Video
    "mp4": "#2980b9",
    "mkv": "#1f618d",
    "avi": "#2874a6",
    "mov": "#2471a3",
    "webm": "#7d3c98",
    "flv": "#1a5276",
    "wmv": "#21618c",
    "m4v": "#3498db",
    # Audio
    "mp3": "#1abc9c",
    "wav": "#16a085",
    "ogg": "#27ae60",
    "flac": "#2ecc71",
    "m4a": "#58d68d",
    "aac": "#48c9b0",
    "wma": "#1e8449",
    # Archives
    "zip": "#e67e22",
    "rar": "#d35400",
    "7z": "#ca6f1e",
    "tar": "#b9770e",
    "gz": "#a04000",
    "bz2": "#935116",
    "xz": "#7e5109",
    # Executables & installers
    "exe": "#c0392b",
    "msi": "#922b21",
    "apk": "#27ae60",
    "dmg": "#7b241c",
    "bin": "#641e16",
    "bat": "#d35400",
    # Code
    "py": "#2ecc71",
    "js": "#f1c40f",
    "ts": "#3498db",
    "html": "#e67e22",
    "css": "#9b59b6",
    "json": "#f39c12",
    "xml": "#16a085",
    "sql": "#2f4f4f",
    "c": "#34495e",
    "cpp": "#2980b9",
    "java": "#c0392b",
    "go": "#5dade2",
    "rs": "#e57373",
    # Misc
    "iso": "#a93226",
    "eps": "#6c3483",
    "psd": "#1b4f72",
    "ai": "#78281f",
    "ttf": "#4a235a",
    "otf": "#512e5f",
}

# Màu dự phòng theo MIME
MIME_FALLBACKS = [
    ("application/pdf", "#e74c3c"),
    ("zip", "#e67e22"),
    ("rar", "#d35400"),
    ("7z", "#ca6f1e"),
    ("image/jpeg", "#f39c12"),
    ("image/png", "#e67e22"),
    ("image/gif", "#9b59b6"),
    ("video/mp4", "#2980b9"),
    ("video/x-matroska", "#1f618d"),
    ("audio/mpeg", "#1abc9c"),
    ("audio/wav", "#16a085"),
    ("text/plain", "#7f8c8d"),
    ("application/octet-stream", "#8e6e53"),
]

# Danh sách màu dự phòng khi không khớp
GENERIC_COLORS = [
    "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
    "#84cc16", "#06b6d4", "#d946ef", "#0ea5e9", "#f59e0b",
]


def _generic_index(name: str) -> int:
    return sum(ord(c) for c in name) % len(GENERIC_COLORS)


def color_for(filename: str, mime_type: str = "") -> str:
    """Mỗi loại file một màu dựa theo phần mở rộng."""
    ext = ""
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext and ext in EXT_COLORS:
        return EXT_COLORS[ext]
    if mime_type:
        mime_lower = mime_type.lower()
        for key, color in MIME_FALLBACKS:
            if key in mime_lower:
                return color
    # Dùng màu tổng quát theo tên/mime
    return GENERIC_COLORS[_generic_index(ext or mime_type or "other")]


def ext_for_name(filename: str) -> str:
    if not filename:
        return "other"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else filename.lower()
    return ext if len(ext) <= 10 else "other"