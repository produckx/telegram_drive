const API_BASE = "/api";

async function apiRequest(method, path, options = {}) {
    const isFormData = options.body instanceof FormData;

    // Do NOT set Content-Type for FormData — let browser add multipart boundary
    const headers = isFormData
        ? { ...(options.headers || {}) }
        : { "Content-Type": "application/json", ...(options.headers || {}) };

    const config = {
        method,
        headers,
        ...options,
    };

    // Stringify JSON bodies, keep FormData as-is
    if (options.body && typeof options.body !== "string" && !(options.body instanceof FormData)) {
        config.body = JSON.stringify(options.body);
    }

    try {
        const response = await fetch(`${API_BASE}${path}`, config);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            // FastAPI validation errors have "detail" as array
            const detail = errorData.detail;
            let message = `HTTP ${response.status}`;
            if (typeof detail === "string") {
                message = detail;
            } else if (Array.isArray(detail)) {
                message = detail.map((d) => d.msg).join("; ");
            } else if (detail && typeof detail === "object") {
                message = detail.message || JSON.stringify(detail);
            }
            throw new Error(message);
        }

        return await response.json();
    } catch (error) {
        console.error(`API Error (${method} ${path}):`, error);
        throw error;
    }
}

// Convenience methods
const api = {
    get: (path, options) => apiRequest("GET", path, options),
    post: (path, body, options) => apiRequest("POST", path, { body, ...options }),
    put: (path, body, options) => apiRequest("PUT", path, { body, ...options }),
    patch: (path, body, options) => apiRequest("PATCH", path, { body, ...options }),
    delete: (path, options) => apiRequest("DELETE", path, options),

    // File upload (multipart)
    upload: (path, formData) => apiRequest("POST", path, {
        body: formData,
    }),
};

// Auth helpers (Telegram session-based, no API key needed anymore)
async function checkAuth() {
    try {
        const res = await api.get("/auth/status");
        return res.is_authorized || false;
    } catch (e) {
        return false;
    }
}

// Export for use in templates
window.api = api;
window.checkAuth = checkAuth;