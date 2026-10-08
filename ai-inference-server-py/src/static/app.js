(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // ---------- Copy buttons ----------
  $$("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        const prev = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = prev; }, 1500);
      } catch { /* clipboard unavailable */ }
    });
  });

  // ---------- Live status ----------
  const fmtUptime = (s) => {
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };
  async function pollHealth() {
    const dot = $("[data-status-dot]");
    const text = $("[data-status-text]");
    const sub = $("[data-status-sub]");
    try {
      const { data } = await (await fetch("/health", { cache: "no-store" })).json();
      dot.className = "dot ok";
      text.textContent = `v${data.version}`;
      sub.textContent = `up ${fmtUptime(data.uptimeSeconds)} · ${data.models} models · ${data.inferences} inferences`;
    } catch {
      dot.className = "dot down";
      text.textContent = "Unreachable";
      sub.textContent = "";
    }
  }
  pollHealth();
  setInterval(() => { if (!document.hidden) pollHealth(); }, 10000);

  // ---------- Try it ----------
  const form = $("#form");
  const input = $("#input");
  const keyWrap = $("#key-wrap");
  const keyInput = $("#key");
  const runBtn = $("#run");
  const reqLine = $("#req-line");
  const resEl = $("#res");
  const statusEl = $("#status");
  const msEl = $("#ms");
  const models = new Map();

  async function api(method, path, body) {
    const headers = {};
    if (body) headers["content-type"] = "application/json";
    if (keyInput.value) headers["x-api-key"] = keyInput.value.trim();
    const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    if (res.status === 401) { keyWrap.hidden = false; keyInput.focus(); }
    let json = null;
    try { json = await res.json(); } catch { /* non-JSON */ }
    return { status: res.status, json, ms: res.headers.get("x-response-time-ms") };
  }

  async function ensureModel(type) {
    if (models.has(type)) return models.get(type);
    const name = `playground-${type}`;
    const list = await api("GET", "/models");
    if (list.status === 401) throw new Error("API key required. Enter it above and run again.");
    let model = list.json?.data?.find((m) => m.name === name);
    if (!model) {
      const created = await api("POST", "/models", { name, type });
      if (!created.json?.success) throw new Error(created.json?.error || "could not create model");
      model = created.json.data;
    }
    models.set(type, model.id);
    return model.id;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) { input.focus(); return; }
    const type = $('input[name="type"]:checked', form).value;
    runBtn.disabled = true;
    try {
      let id = await ensureModel(type);
      let r = await api("POST", `/models/${id}/infer`, { input: text });
      if (r.status === 404) { models.delete(type); id = await ensureModel(type); r = await api("POST", `/models/${id}/infer`, { input: text }); }
      reqLine.textContent = `POST /models/${id.slice(0, 8)}…/infer`;
      resEl.textContent = JSON.stringify(r.json, null, 2);
      statusEl.textContent = String(r.status);
      statusEl.className = r.status < 400 ? "ok" : "err";
      msEl.textContent = r.ms ? `${r.ms} ms` : "";
      pollHealth();
    } catch (err) {
      resEl.textContent = err.message;
      statusEl.textContent = "error";
      statusEl.className = "err";
      msEl.textContent = "";
    } finally {
      runBtn.disabled = false;
    }
  });

  input.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") form.requestSubmit();
  });
})();
