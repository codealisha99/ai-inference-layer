(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const clamp = (n, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, n));
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.documentElement.classList.add("js");

  // ---------- Header + menu ----------
  const header = $("#site-header");
  const menuBtn = $("#menu-btn");
  const menu = $("#menu");

  const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 24);

  function setMenu(open) {
    menu.hidden = !open;
    menuBtn.setAttribute("aria-expanded", String(open));
    $(".menu-label", menuBtn).textContent = open ? "Close" : "Menu";
    document.body.classList.toggle("menu-open", open);
  }
  menuBtn.addEventListener("click", () => setMenu(menu.hidden));
  menu.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) { setMenu(false); menuBtn.focus(); }
  });

  // ---------- Blueprint draw-on-scroll ----------
  const blueprint = $("#blueprint");
  const draws = $$(".draw", blueprint);
  const fades = $$(".fade", blueprint);
  const hint = $("[data-scroll-hint]");
  const local = (p, s, e) => clamp((p - s) / (e - s));

  function paintBlueprint() {
    let p = 1;
    if (!reduceMotion) {
      const r = blueprint.getBoundingClientRect();
      const vh = window.innerHeight;
      p = clamp((vh * 0.95 - r.top) / (r.height * 0.9));
    }
    draws.forEach((el) => {
      el.style.strokeDashoffset = String(1 - local(p, +el.dataset.s, +el.dataset.e));
    });
    fades.forEach((el) => {
      el.style.opacity = String(local(p, +el.dataset.s, +el.dataset.e));
    });
    if (hint) hint.textContent = p >= 0.999 ? "Drawn" : `Scroll to finish`;
  }

  let ticking = false;
  const onFrame = () => {
    ticking = false;
    onScroll();
    paintBlueprint();
  };
  const requestFrame = () => { if (!ticking) { ticking = true; requestAnimationFrame(onFrame); } };
  window.addEventListener("scroll", requestFrame, { passive: true });
  window.addEventListener("resize", requestFrame);
  onFrame();

  // ---------- Reveal on scroll ----------
  const reveals = $$(".reveal");
  if ("IntersectionObserver" in window && !reduceMotion) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("in"));
  }

  // ---------- Accordion ----------
  $$("[data-accordion] .acc-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = btn.closest(".acc-item");
      const open = !item.classList.contains("open");
      $$(".acc-item", item.parentElement).forEach((it) => {
        const isThis = it === item;
        it.classList.toggle("open", isThis && open);
        $(".acc-btn", it).setAttribute("aria-expanded", String(isThis && open));
      });
    });
  });

  // ---------- Carousel ----------
  const carousel = $("[data-carousel]");
  if (carousel) {
    const slides = $$(".slide", carousel);
    const dots = $$(".dot", carousel);
    const labels = $$(".slide-labels li", carousel);
    const counter = $("[data-count-label]", carousel);
    let index = 0;

    const show = (i) => {
      index = (i + slides.length) % slides.length;
      slides.forEach((s, n) => { s.hidden = n !== index; s.classList.toggle("active", n === index); });
      dots.forEach((d, n) => {
        d.classList.toggle("on", n === index);
        if (n === index) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current");
      });
      labels.forEach((l, n) => l.classList.toggle("on", n === index));
      counter.textContent = `${String(index + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
    };
    $("[data-prev]", carousel).addEventListener("click", () => show(index - 1));
    $("[data-next]", carousel).addEventListener("click", () => show(index + 1));
    dots.forEach((d, n) => d.addEventListener("click", () => show(n)));
    labels.forEach((l, n) => { l.style.cursor = "pointer"; l.addEventListener("click", () => show(n)); });
    carousel.tabIndex = 0;
    carousel.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") show(index + 1);
      if (e.key === "ArrowLeft") show(index - 1);
    });
    show(0);
  }

  // ---------- Copy buttons ----------
  $$("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = btn.dataset.copy;
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch { /* ignore */ }
        ta.remove();
      }
      const prev = btn.textContent;
      btn.textContent = "Copied"; btn.classList.add("done");
      setTimeout(() => { btn.textContent = prev; btn.classList.remove("done"); }, 1600);
    });
  });

  // ---------- Live status ----------
  const fmtUptime = (s) => {
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };
  async function pollHealth() {
    const dots = $$("[data-status-dot]");
    const texts = $$("[data-status-text]");
    const sub = $("[data-status-sub]");
    try {
      const res = await fetch("/health", { cache: "no-store" });
      const { data } = await res.json();
      dots.forEach((d) => { d.className = "status-dot ok"; });
      texts.forEach((t) => { t.textContent = `Server ${data.status}, v${data.version}`; });
      if (sub) sub.textContent = `up ${fmtUptime(data.uptimeSeconds)}, ${data.models} models, ${data.inferences} inferences`;
      $$("[data-version]").forEach((v) => { v.textContent = `, v${data.version}`; });
    } catch {
      dots.forEach((d) => { d.className = "status-dot down"; });
      texts.forEach((t) => { t.textContent = "Server unreachable"; });
      if (sub) sub.textContent = "";
    }
  }
  pollHealth();
  setInterval(() => { if (!document.hidden) pollHealth(); }, 5000);

  // ---------- Playground ----------
  const form = $("#pg-form");
  if (form) {
    const input = $("#pg-input");
    const reqEl = $("#pg-req");
    const reqLine = $("#pg-req-line");
    const resEl = $("#pg-res");
    const statusEl = $("#pg-status");
    const msEl = $("#pg-ms");
    const histEl = $("#pg-history");
    const countEl = $("#pg-count");
    const runBtn = $("#pg-run");

    const examples = {
      "text-classification": [
        "I love how simple and fast this is.",
        "This was a terrible, disappointing experience.",
        "The package arrived on Tuesday.",
        "That is not good at all.",
      ],
      "text-generation": ["Explain tokenization in one line.", "Write a haiku about servers.", "Summarise the CAP theorem."],
      embedding: ["hello world", "interior design studio", "the quick brown fox"],
    };
    const typeValue = () => $('input[name="type"]:checked', form).value;
    const modelCache = new Map();
    const histories = new Map();

    const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const highlight = (obj) => esc(JSON.stringify(obj, null, 2)).replace(
      /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
      (m, str, colon, lit, num) => {
        if (str) return colon ? `<span class="k">${str}</span>${colon}` : `<span class="s">${str}</span>`;
        if (lit) return `<span class="b">${lit}</span>`;
        return `<span class="n">${num}</span>`;
      },
    );

    const keyWrap = $("#pg-key-wrap");
    const keyInput = $("#pg-key");

    async function api(method, path, body) {
      const headers = {};
      if (body) headers["content-type"] = "application/json";
      if (keyInput.value) headers["x-api-key"] = keyInput.value.trim();
      const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
      if (res.status === 401) {
        keyWrap.hidden = false;
        keyInput.focus();
      }
      let json = null;
      try { json = await res.json(); } catch { /* non-JSON */ }
      return { status: res.status, json, ms: res.headers.get("x-response-time-ms") };
    }

    async function ensureModel(type) {
      if (modelCache.has(type)) return modelCache.get(type);
      const name = `playground-${type}`;
      const list = await api("GET", "/models");
      if (list.status === 401) throw new Error("API key required. Enter it above and run again.");
      let model = list.json?.data?.find((m) => m.name === name);
      if (!model) {
        const created = await api("POST", "/models", { name, type });
        if (!created.json?.success) throw new Error(created.json?.error || "could not create model");
        model = created.json.data;
      }
      modelCache.set(type, model.id);
      return model.id;
    }

    async function refreshHistory(type) {
      const id = modelCache.get(type);
      if (!id) return;
      const r = await api("GET", `/models/${id}/inferences`);
      const items = r.json?.data || [];
      histories.set(type, items);
      renderHistory(type);
    }

    function renderHistory(type) {
      const items = (histories.get(type) || []).slice(-5).reverse();
      countEl.textContent = items.length ? `(${(histories.get(type) || []).length} stored)` : "";
      histEl.replaceChildren();
      if (!items.length) {
        const li = document.createElement("li");
        li.className = "empty"; li.textContent = "Nothing yet. Run one.";
        histEl.append(li);
        return;
      }
      items.forEach((inf) => {
        const li = document.createElement("li");
        const b = document.createElement("button");
        b.type = "button";
        const a = document.createElement("span"); a.textContent = inf.input;
        const c = document.createElement("span"); c.textContent = `${inf.latencyMs} ms`;
        b.append(a, c);
        b.addEventListener("click", () => {
          input.value = inf.input;
          showResult(inf.modelId, inf.input, 200, { success: true, data: inf, error: null }, null, true);
        });
        li.append(b);
        histEl.append(li);
      });
    }

    function showResult(modelId, text, status, json, ms, replay = false) {
      reqLine.textContent = replay ? `GET /models/${modelId.slice(0, 8)}…/inferences` : `POST /models/${modelId.slice(0, 8)}…/infer`;
      reqEl.textContent = JSON.stringify({ input: text }, null, 2);
      resEl.innerHTML = highlight(json);
      statusEl.textContent = String(status);
      statusEl.className = `badge ${status < 400 ? "ok" : "err"}`;
      msEl.textContent = ms ? `${ms} ms` : "";
    }

    async function run(e) {
      e?.preventDefault();
      const text = input.value.trim();
      if (!text) { input.focus(); return; }
      const type = typeValue();
      form.classList.add("busy"); runBtn.disabled = true;
      try {
        let id = await ensureModel(type);
        let r = await api("POST", `/models/${id}/infer`, { input: text });
        if (r.status === 404) { modelCache.delete(type); id = await ensureModel(type); r = await api("POST", `/models/${id}/infer`, { input: text }); }
        showResult(id, text, r.status, r.json, r.ms);
        await refreshHistory(type);
        pollHealth();
      } catch (err) {
        reqEl.textContent = JSON.stringify({ input: text }, null, 2);
        resEl.textContent = `Could not reach the server: ${err.message}`;
        statusEl.textContent = "error"; statusEl.className = "badge err"; msEl.textContent = "";
      } finally {
        form.classList.remove("busy"); runBtn.disabled = false;
      }
    }

    form.addEventListener("submit", run);
    input.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(e); });
    $("#pg-example").addEventListener("click", () => {
      const pool = examples[typeValue()];
      const others = pool.filter((x) => x !== input.value);
      input.value = others[Math.floor(Math.random() * others.length)] || pool[0];
      reqEl.textContent = JSON.stringify({ input: input.value }, null, 2);
    });
    $$('input[name="type"]', form).forEach((r) => r.addEventListener("change", () => {
      const pool = examples[typeValue()];
      if (!Object.values(examples).flat().includes(input.value.trim())) return;
      input.value = pool[0];
      reqEl.textContent = JSON.stringify({ input: input.value }, null, 2);
      renderHistory(typeValue());
    }));
  }
})();
