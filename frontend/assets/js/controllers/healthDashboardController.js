import { fetchSystemHealth } from "../services/healthService.js";
import { formatLatency, formatTimestamp, statusMeta } from "../utils/status.js";

/**
 * Wires the health landing page to real backend data. Every refresh clears
 * the previous render before awaiting the new response, so a failed retry
 * can never leave a stale "healthy" banner on screen.
 */
export function createHealthDashboardController({
  document,
  fetchImpl,
  elements: overrideElements,
} = {}) {
  const elements = overrideElements || {
    banner: document.getElementById("status-banner"),
    bannerText: document.getElementById("status-banner-text"),
    checksList: document.getElementById("checks-list"),
    retryButton: document.getElementById("retry-button"),
    lastUpdated: document.getElementById("last-updated"),
    liveRegion: document.getElementById("live-region"),
  };

  function setBannerState(stateClass, text) {
    elements.banner.className = `status-banner status-banner--${stateClass}`;
    elements.bannerText.textContent = text;
    elements.liveRegion.textContent = text;
  }

  function setLoading() {
    elements.retryButton.disabled = true;
    elements.checksList.innerHTML = "";
    elements.lastUpdated.textContent = "—";
    setBannerState("loading", "Dang kiem tra trang thai he thong...");
  }

  function setError(message) {
    elements.checksList.innerHTML = "";
    elements.lastUpdated.textContent = "—";
    setBannerState("error", message);
    elements.retryButton.disabled = false;
  }

  function renderChecks(checks) {
    elements.checksList.innerHTML = "";
    Object.entries(checks).forEach(([name, check]) => {
      const meta = statusMeta(check.status);
      const item = document.createElement("li");
      item.className = `check-card check-card--${check.status}`;

      const title = document.createElement("span");
      title.className = "check-card__name";
      title.textContent = name;

      const badge = document.createElement("span");
      badge.className = "check-card__badge";
      badge.textContent = meta.label;

      const latency = document.createElement("span");
      latency.className = "check-card__latency";
      latency.textContent = formatLatency(check.latency_ms);

      item.append(title, badge, latency);
      elements.checksList.appendChild(item);
    });
  }

  function setSuccess(payload) {
    const meta = statusMeta(payload.status);
    renderChecks(payload.checks);
    elements.lastUpdated.textContent = formatTimestamp(payload.timestamp);
    setBannerState(payload.status, meta.bannerText);
    elements.retryButton.disabled = false;
  }

  async function refresh() {
    setLoading();
    try {
      const payload = await fetchSystemHealth(fetchImpl);
      setSuccess(payload);
    } catch (error) {
      setError("Khong the ket noi toi backend. Vui long thu lai.");
    }
  }

  elements.retryButton.addEventListener("click", () => {
    refresh();
  });

  return { refresh };
}
