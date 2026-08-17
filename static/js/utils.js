// Utility functions

function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function formatDateTime(dateString) {
    if (!dateString) return "-";
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    return date.toLocaleString("vi-VN");
}

function formatDate(dateString) {
    if (!dateString) return "-";
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    return date.toLocaleDateString("vi-VN");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function getFileExtension(filename) {
    const parts = filename.split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

function getFileIcon(name, mimeType) {
    const ext = getFileExtension(name);
    const imageExts = ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"];
    const videoExts = ["mp4", "mkv", "avi", "mov", "webm"];
    const audioExts = ["mp3", "wav", "ogg", "flac", "m4a"];
    const archiveExts = ["zip", "rar", "7z", "tar", "gz"];
    const docExts = ["pdf", "doc", "docx", "txt", "md", "rtf"];

    if (mimeType?.startsWith("image/") || imageExts.includes(ext)) return "fa-image";
    if (mimeType?.startsWith("video/") || videoExts.includes(ext)) return "fa-video";
    if (mimeType?.startsWith("audio/") || audioExts.includes(ext)) return "fa-music";
    if (archiveExts.includes(ext)) return "fa-file-archive";
    if (docExts.includes(ext)) return "fa-file-text";
    return "fa-file";
}

function toQueryString(params) {
    const query = Object.entries(params)
        .filter(([, value]) => value !== null && value !== undefined && value !== "")
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join("&");
    return query ? `?${query}` : "";
}

window.debounce = debounce;
window.formatDateTime = formatDateTime;
window.formatDate = formatDate;
window.escapeHtml = escapeHtml;
window.getFileExtension = getFileExtension;
window.getFileIcon = getFileIcon;
window.toQueryString = toQueryString;