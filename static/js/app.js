// Global application scripts

document.addEventListener("DOMContentLoaded", () => {
    initNavbar();
    initToasts();
});

function initNavbar() {
    const authBtn = document.getElementById("authBtn");
    if (!authBtn) return;

    // Check Telegram auth status to decide the button
    checkAuth().then((isAuth) => {
        if (isAuth) {
            authBtn.textContent = "Đăng xuất";
            authBtn.classList.remove("btn-primary");
            authBtn.classList.add("btn-outline-light");
            authBtn.href = "/auth/login";
        } else {
            authBtn.textContent = "Đăng nhập";
            authBtn.href = "/auth/login";
        }
    });
}

function initToasts() {
    window.showToast = (message, type = "info") => {
        const container = document.getElementById("toastContainer") || createToastContainer();
        const id = `toast-${Date.now()}`;
        const colorClass = {
            success: "bg-success text-white",
            error: "bg-danger text-white",
            warning: "bg-warning",
            info: "bg-info text-white",
        }[type] || "bg-info text-white";

        const toastHtml = `
        <div id="${id}" class="toast ${colorClass}" role="alert" aria-live="assertive">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>`;

        container.insertAdjacentHTML("beforeend", toastHtml);
        const toastEl = document.getElementById(id);
        const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
        toast.show();
        toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove());
    };
}

function createToastContainer() {
    const container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
    return container;
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

window.formatBytes = formatBytes;