export const STATUS_META = {
  healthy: {
    label: "Healthy",
    bannerText: "Tat ca dich vu dang hoat dong binh thuong.",
  },
  degraded: {
    label: "Degraded",
    bannerText: "Mot so dich vu phu thuoc dang gap su co.",
  },
  unavailable: {
    label: "Unavailable",
    bannerText: "Dich vu phu thuoc hien khong kha dung.",
  },
  unknown: {
    label: "Unknown",
    bannerText: "Khong xac dinh duoc trang thai.",
  },
};

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.unknown;
}

export function isKnownStatus(value) {
  return Object.prototype.hasOwnProperty.call(STATUS_META, value);
}

export function formatLatency(latencyMs) {
  if (typeof latencyMs !== "number" || Number.isNaN(latencyMs)) {
    return "—";
  }
  return `${latencyMs.toFixed(1)} ms`;
}

export function formatTimestamp(isoString) {
  if (!isoString) {
    return "—";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleString();
}
