import { createHealthDashboardController } from "./healthDashboardController.js";

document.addEventListener("DOMContentLoaded", () => {
  const controller = createHealthDashboardController({
    document,
    fetchImpl: window.fetch.bind(window),
  });
  controller.refresh();
});
