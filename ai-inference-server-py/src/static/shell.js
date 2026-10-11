(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const announce = (message) => {
    const region = $("#announcement");
    if (region) region.textContent = message;
  };
  const copy = async (button, text) => {
    const label = button.textContent;
    button.disabled = true;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
      announce("Copied to clipboard.");
    } catch {
      button.textContent = "Copy failed";
      announce("Clipboard unavailable. Select the code and copy it manually.");
    }
    setTimeout(() => {
      button.textContent = label;
      button.disabled = false;
      button.dispatchEvent(new Event("copycomplete"));
    }, 1800);
  };
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => copy(button, button.dataset.copy));
  });
  window.inferenceUI = { announce, copy };

  const formatUptime = (seconds) => seconds < 60 ? `${Math.floor(seconds)}s`
    : seconds < 3600 ? `${Math.floor(seconds / 60)}m` : `${Math.floor(seconds / 3600)}h`;
  let checking = false;
  async function pollHealth() {
    if (checking) return;
    checking = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/health", { cache: "no-store", signal: controller.signal });
      const json = await response.json();
      if (!response.ok || !json.success || json.data?.status !== "ok") throw new Error("unavailable");
      const data = json.data;
      $("[data-status-dot]").className = "dot ok";
      $("[data-status-text]").textContent = `API online · v${data.version}`;
      $("[data-status-sub]").textContent = `Uptime ${formatUptime(data.uptimeSeconds)} · ${data.models} models · ${data.inferences} inferences · ${data.storage}`;
    } catch {
      $("[data-status-dot]").className = "dot down";
      $("[data-status-text]").textContent = "API unavailable";
      $("[data-status-sub]").textContent = "Server unreachable. Status checks retry automatically.";
    } finally {
      clearTimeout(timeout);
      checking = false;
    }
  }
  window.inferenceUI.pollHealth = pollHealth;
  pollHealth();
  setInterval(() => { if (!document.hidden) pollHealth(); }, 15000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollHealth(); });

  const updateNavigation = () => {
    const path = location.pathname.replace(/\/index\.html$/, "").replace(/\/$/, "") || "/";
    document.querySelectorAll(".header nav a").forEach((link) => {
      const href = link.getAttribute("href");
      link.removeAttribute("aria-current");
      if (href === path + location.hash) link.setAttribute("aria-current", location.hash ? "location" : "page");
      if (href === "/docs" && path === "/redoc") link.setAttribute("aria-current", "page");
    });
  };
  updateNavigation();
  window.addEventListener("hashchange", updateNavigation);
})();
