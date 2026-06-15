const STORAGE_KEY = "sentinelllm.apiKey";

const elements = {
    apiKey: document.querySelector("#apiKey"),
    refreshButton: document.querySelector("#refreshButton"),
    keyNote: document.querySelector("#keyNote"),
    errorMessage: document.querySelector("#errorMessage"),
    connectionState: document.querySelector("#connectionState"),
    healthValue: document.querySelector("#healthValue"),
    healthDetail: document.querySelector("#healthDetail"),
    requestTotal: document.querySelector("#requestTotal"),
    uptimeValue: document.querySelector("#uptimeValue"),
    cacheValue: document.querySelector("#cacheValue"),
    cacheDetail: document.querySelector("#cacheDetail"),
    statusCounts: document.querySelector("#statusCounts"),
    methodCounts: document.querySelector("#methodCounts"),
    logRows: document.querySelector("#logRows"),
    logCount: document.querySelector("#logCount")
};

function setLoading(isLoading) {
    elements.refreshButton.disabled = isLoading;
    elements.refreshButton.textContent = isLoading ? "Loading..." : "Refresh dashboard";
}

function setConnection(state, message) {
    elements.connectionState.className = `connection ${state}`;
    elements.connectionState.querySelector("span:last-child").textContent = message;
}

function showError(message) {
    elements.errorMessage.textContent = message;
    elements.errorMessage.classList.remove("hidden");
}

function clearError() {
    elements.errorMessage.textContent = "";
    elements.errorMessage.classList.add("hidden");
}

async function fetchJson(url, apiKey = "") {
    const headers = apiKey ? { "X-API-Key": apiKey } : {};
    const response = await fetch(url, { headers });
    const payload = await response.json().catch(() => null);

    if (!response.ok) {
        const message = payload?.error?.message || `Request failed with status ${response.status}`;
        throw new Error(message);
    }

    if (!payload?.success) {
        throw new Error(payload?.error?.message || "The backend returned an invalid response.");
    }

    return payload.data;
}

function formatUptime(seconds) {
    if (!Number.isFinite(seconds)) {
        return "--";
    }

    const wholeSeconds = Math.floor(seconds);
    const hours = Math.floor(wholeSeconds / 3600);
    const minutes = Math.floor((wholeSeconds % 3600) / 60);
    const remainingSeconds = wholeSeconds % 60;

    return [hours, minutes, remainingSeconds]
        .map((value) => String(value).padStart(2, "0"))
        .join(":");
}

function renderCounts(container, counts) {
    container.replaceChildren();
    const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);

    if (!entries.length) {
        const empty = document.createElement("p");
        empty.className = "empty-state";
        empty.textContent = "No request data recorded.";
        container.append(empty);
        return;
    }

    for (const [label, count] of entries) {
        const chip = document.createElement("div");
        chip.className = "count-chip";

        const name = document.createElement("span");
        name.textContent = label;

        const value = document.createElement("strong");
        value.textContent = count.toLocaleString();

        chip.append(name, value);
        container.append(chip);
    }
}

function formatTimestamp(timestamp) {
    if (!timestamp) {
        return "--";
    }

    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
}

function statusClass(status) {
    const numericStatus = Number(status);

    if (numericStatus >= 500) {
        return "status-badge error";
    }

    if (numericStatus >= 400) {
        return "status-badge warn";
    }

    return "status-badge";
}

function renderLogs(logs) {
    elements.logRows.replaceChildren();
    elements.logCount.textContent = `${logs.length} ${logs.length === 1 ? "entry" : "entries"}`;

    if (!logs.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 6;
        cell.className = "empty-state";
        cell.textContent = "No request logs found.";
        row.append(cell);
        elements.logRows.append(row);
        return;
    }

    for (const log of [...logs].reverse()) {
        const row = document.createElement("tr");
        const values = [
            formatTimestamp(log.timestamp),
            log.method || "--",
            log.endpoint || log.raw || "--"
        ];

        for (const value of values) {
            const cell = document.createElement("td");
            cell.textContent = String(value);
            row.append(cell);
        }

        const statusCell = document.createElement("td");
        const statusBadge = document.createElement("span");
        statusBadge.className = statusClass(log.status);
        statusBadge.textContent = log.status ?? "--";
        statusCell.append(statusBadge);
        row.append(statusCell);

        const latencyCell = document.createElement("td");
        latencyCell.textContent = Number.isFinite(log.latency_ms)
            ? `${log.latency_ms} ms`
            : "--";
        row.append(latencyCell);

        const requestCell = document.createElement("td");
        requestCell.textContent = log.request_id || "--";
        requestCell.title = log.request_id || "";
        row.append(requestCell);

        elements.logRows.append(row);
    }
}

function renderHealth(health) {
    elements.healthValue.textContent = health.status === "ok" ? "Operational" : health.status;
    elements.healthDetail.textContent = health.service || "SentinelLLM backend";
}

function renderMetrics(metrics) {
    const requests = metrics.requests || {};
    elements.requestTotal.textContent = Number(requests.total_requests || 0).toLocaleString();
    elements.uptimeValue.textContent = formatUptime(metrics.uptime_seconds);
    elements.cacheValue.textContent = Number(metrics.cache?.items || 0).toLocaleString();
    elements.cacheDetail.textContent = `TTL ${metrics.cache?.ttl_seconds || 0}s`;
    renderCounts(elements.statusCounts, requests.status_counts);
    renderCounts(elements.methodCounts, requests.method_counts);
}

async function refreshDashboard() {
    const apiKey = elements.apiKey.value.trim();

    localStorage.setItem(STORAGE_KEY, apiKey);
    elements.keyNote.textContent = apiKey
        ? "API key saved in localStorage."
        : "Enter an API key to load protected metrics and logs.";

    clearError();
    setLoading(true);
    setConnection("", "Connecting...");

    try {
        const health = await fetchJson("/api/v1/health");
        renderHealth(health);

        if (!apiKey) {
            throw new Error("API key is required for metrics and recent logs.");
        }

        const [metrics, recentLogs] = await Promise.all([
            fetchJson("/api/v1/metrics", apiKey),
            fetchJson("/api/v1/logs/recent?limit=20", apiKey)
        ]);

        renderMetrics(metrics);
        renderLogs(recentLogs.logs || []);
        setConnection("online", "Backend connected");
    } catch (error) {
        showError(error.message);
        setConnection("error", "Connection issue");
    } finally {
        setLoading(false);
    }
}

elements.apiKey.value = localStorage.getItem(STORAGE_KEY) || "";
elements.apiKey.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEY, elements.apiKey.value.trim());
});
elements.apiKey.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        refreshDashboard();
    }
});
elements.refreshButton.addEventListener("click", refreshDashboard);

refreshDashboard();
