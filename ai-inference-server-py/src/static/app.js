(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const { announce, copy, pollHealth } = window.inferenceUI;
  const form = $("#form");
  const input = $("#input");
  const keyInput = $("#key");
  const keyWrap = $("#key-wrap");
  const keyToggle = $("#key-toggle");
  const run = $("#run");
  const status = $("#status");
  const panel = $("#response-panel");
  const summary = $("#response-summary");
  const result = $("#res");
  const error = $("#input-error");
  const copyButton = $("#copy-response");
  const radios = [...form.querySelectorAll('input[name="type"]')];
  const models = new Map();
  let responseText = "";
  let busy = false;
  const engines = {
    "text-classification": { hint: "Read sentiment as a label and a score.", placeholder: "Enter text to classify…" },
    "text-generation": { hint: "Get a deterministic text response for your integration.", placeholder: "Enter a prompt…" },
    embedding: { hint: "Turn text into a stable, unit-length vector.", placeholder: "Enter text to embed…" },
  };
  const showKey = (open) => {
    keyWrap.hidden = !open;
    keyToggle.setAttribute("aria-expanded", String(open));
    if (open) keyInput.focus();
  };
  keyToggle.addEventListener("click", () => showKey(keyWrap.hidden));
  keyInput.addEventListener("input", () => models.clear());
  const clearError = () => {
    error.hidden = true;
    error.textContent = "";
    input.removeAttribute("aria-invalid");
  };
  input.addEventListener("input", () => {
    $("#char-count").textContent = `${input.value.length.toLocaleString("en-US")} / 2,000`;
    clearError();
  });
  input.dispatchEvent(new Event("input"));
  radios.forEach((radio) => radio.addEventListener("change", () => {
    const engine = engines[radio.value];
    $("#engine-hint").textContent = engine.hint;
    input.placeholder = engine.placeholder;
    clearError();
  }));

  class ApiError extends Error {
    constructor(message, response) {
      super(message);
      this.response = response;
    }
  }
  async function api(method, path, body) {
    $("#req-line").textContent = `${method} ${path}`;
    const headers = {};
    if (body) headers["content-type"] = "application/json";
    if (keyInput.value.trim()) headers["x-api-key"] = keyInput.value.trim();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, { method, headers, signal: controller.signal, body: body ? JSON.stringify(body) : undefined });
      let json;
      try { json = await response.json(); } catch { json = null; }
      const value = { status: response.status, json, ms: response.headers.get("x-response-time-ms") };
      if (response.status === 401) showKey(true);
      if (!response.ok || !json?.success) {
        let message = json?.error || `The server returned HTTP ${response.status}. Please try again.`;
        if (response.status === 401) message = "Enter a valid API key, then run the request again.";
        if (response.status === 429) {
          const wait = Number(response.headers.get("retry-after"));
          message = wait > 0 ? `Rate limit reached. Try again in ${Math.ceil(wait)} seconds.` : "Rate limit reached. Wait a moment, then try again.";
        }
        throw new ApiError(message, value);
      }
      return value;
    } finally {
      clearTimeout(timeout);
    }
  }
  async function findModel(type) {
    const list = await api("GET", "/models");
    return list.json.data.find((model) => model.name === `playground-${type}` && model.type === type);
  }
  async function ensureModel(type) {
    if (models.has(type)) return models.get(type);
    let model = await findModel(type);
    if (!model) {
      try {
        model = (await api("POST", "/models", { name: `playground-${type}`, type })).json.data;
      } catch (failure) {
        if (failure.response?.status !== 409) throw failure;
        // Another tab can register the shared playground model between our read and write.
        model = await findModel(type);
        if (!model) throw failure;
      }
    }
    models.set(type, model.id);
    return model.id;
  }
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function showSummary(type, output) {
    summary.replaceChildren();
    if (type === "text-generation") {
      summary.append(element("h4", "Generated text"), element("p", output.text, "output-text"));
    } else {
      const fields = type === "embedding" ? [["Output", "Vector"], ["Dimensions", output.embedding.length]] : [["Sentiment", output.label], ["Score", output.score]];
      const grid = element("dl", "", "output-grid");
      fields.forEach(([label, value]) => {
        const item = element("div", "");
        item.append(element("dt", label), element("dd", String(value)));
        grid.append(item);
      });
      summary.append(grid);
      if (type === "embedding") summary.append(element("p", "The complete vector is included in the JSON response below."));
    }
  }
  function setResponse(response) {
    status.textContent = `HTTP ${response.status}`;
    status.className = response.status < 400 ? "badge ok" : "badge err";
    $("#ms").textContent = response.ms ? `${response.ms} ms` : "";
    responseText = response.json ? JSON.stringify(response.json, null, 2) : "";
    result.textContent = responseText || "The server did not return a JSON response.";
    copyButton.disabled = !responseText;
  }
  copyButton.addEventListener("click", () => copy(copyButton, responseText));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    clearError();
    const text = input.value.trim();
    if (!text) {
      error.textContent = "Enter some text before running an inference.";
      error.hidden = false;
      input.setAttribute("aria-invalid", "true");
      input.focus();
      announce(error.textContent);
      return;
    }
    const type = form.querySelector('input[name="type"]:checked').value;
    busy = true;
    run.disabled = true;
    run.textContent = "Running…";
    radios.forEach((radio) => { radio.disabled = true; });
    form.setAttribute("aria-busy", "true");
    panel.dataset.state = "loading";
    status.textContent = "Running";
    status.className = "badge";
    $("#ms").textContent = "";
    copyButton.disabled = true;
    summary.replaceChildren(element("h4", "Running your request…"), element("p", "Registering the model if needed, then sending your input to the server."));
    result.textContent = "Waiting for the server…";
    announce("Running inference.");
    try {
      let id = await ensureModel(type);
      let response;
      try {
        response = await api("POST", `/models/${id}/infer`, { input: text });
      } catch (failure) {
        if (failure.response?.status !== 404) throw failure;
        models.delete(type);
        id = await ensureModel(type);
        response = await api("POST", `/models/${id}/infer`, { input: text });
      }
      $("#req-line").textContent = `POST /models/${id}/infer`;
      setResponse(response);
      showSummary(type, response.json.data.output);
      panel.dataset.state = "success";
      announce(`Inference completed. HTTP ${response.status}.`);
      pollHealth();
    } catch (failure) {
      panel.dataset.state = "error";
      const message = failure instanceof ApiError ? failure.message : failure.name === "AbortError" ? "The request timed out. Check the server status and try again." : "Could not reach the API. Check your connection and run the request again.";
      if (failure.response) setResponse(failure.response);
      else {
        status.textContent = "Request failed";
        status.className = "badge err";
        result.textContent = "No response received.";
        responseText = "";
        copyButton.disabled = true;
      }
      summary.replaceChildren(element("h4", "Request unsuccessful"), element("p", message));
      announce(message);
    } finally {
      busy = false;
      run.disabled = false;
      run.textContent = "Run inference";
      radios.forEach((radio) => { radio.disabled = false; });
      form.removeAttribute("aria-busy");
    }
  });
  input.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      form.requestSubmit();
    }
  });
})();
