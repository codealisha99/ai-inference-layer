(() => {
  "use strict";
  const kind = document.body.dataset.docs;
  const feedback = document.querySelector("#docs-feedback");
  const message = document.querySelector("#docs-message");
  const retry = document.querySelector("#docs-retry");
  const content = document.querySelector("#api-reference");
  const keyInput = document.querySelector("#docs-key");
  const value = (token) => getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  document.querySelectorAll(".docs-tabs a").forEach((link) => {
    if (link.getAttribute("href") === location.pathname) link.setAttribute("aria-current", "page");
  });
  if (kind === "redoc") document.querySelector("#docs-key-wrap").hidden = true;
  const enableViewerKeyboardAccess = () => {
    content.querySelectorAll("pre").forEach((block) => {
      block.tabIndex = 0;
      block.setAttribute("aria-label", "Code sample");
    });
    // Swagger nests a permalink inside its expand button. Keep the link as a sibling.
    content.querySelectorAll(".opblock-summary-control a[href]").forEach((link) => {
      const button = link.closest("button");
      if (!button.parentElement.querySelector(".operation-link")) {
        const permalink = document.createElement("a");
        permalink.className = "operation-link";
        permalink.href = link.getAttribute("href");
        permalink.textContent = "Link";
        permalink.setAttribute("aria-label", `Link to ${button.textContent.trim()}`);
        button.after(permalink);
      }
      link.removeAttribute("href");
      link.setAttribute("role", "presentation");
    });
  };
  // Documentation viewers replace samples when an operation or response tab changes.
  new MutationObserver(enableViewerKeyboardAccess).observe(content, { childList: true, subtree: true });
  let loading = false;
  async function load() {
    if (loading) return;
    loading = true;
    feedback.hidden = false;
    retry.hidden = true;
    message.textContent = "Loading the API reference…";
    content.replaceChildren();
    try {
      const response = await fetch("/openapi.json", { signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error("The API specification is unavailable.");
      const spec = await response.json();
      if (kind === "swagger") {
        const stylesheet = document.createElement("link");
        stylesheet.rel = "stylesheet";
        stylesheet.href = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.1/swagger-ui.css";
        if (!document.querySelector('link[href="' + stylesheet.href + '"]')) document.head.prepend(stylesheet);
      }
      const global = kind === "swagger" ? "SwaggerUIBundle" : "Redoc";
      if (!window[global]) await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = kind === "swagger" ? "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.1/swagger-ui-bundle.js" : "https://cdn.jsdelivr.net/npm/redoc@2.5.4/bundles/redoc.standalone.js";
        const timeout = setTimeout(() => { script.remove(); reject(new Error("The documentation viewer timed out.")); }, 20000);
        script.onload = () => { clearTimeout(timeout); resolve(); };
        script.onerror = () => { clearTimeout(timeout); script.remove(); reject(new Error("The documentation viewer could not be loaded.")); };
        document.head.append(script);
      });
      if (kind === "swagger") {
        window.SwaggerUIBundle({
          spec, dom_id: "#api-reference", layout: "BaseLayout", deepLinking: true,
          docExpansion: "none", filter: true, displayRequestDuration: true,
          persistAuthorization: false, validatorUrl: null,
          requestInterceptor: (request) => {
            if (new URL(request.url, location.href).origin === location.origin && keyInput.value.trim()) request.headers["X-API-Key"] = keyInput.value.trim();
            return request;
          },
          onComplete: () => { feedback.hidden = true; },
          presets: [window.SwaggerUIBundle.presets.apis],
        });
      } else {
        await new Promise((resolve, reject) => window.Redoc.init(spec, {
          disableGoogleFont: true, hideDownloadButton: false, nativeScrollbars: true,
          theme: {
            colors: { primary: { main: value("--brand") }, text: { primary: value("--text"), secondary: value("--text-secondary") } },
            typography: { fontFamily: value("--sans"), fontSize: "15px", headings: { fontFamily: value("--sans"), fontWeight: "600" }, code: { fontFamily: value("--mono") } },
            sidebar: { backgroundColor: value("--surface"), textColor: value("--text-secondary") },
            rightPanel: { backgroundColor: value("--code-bg"), textColor: value("--code-text") },
          },
        }, content, (error) => error ? reject(error) : resolve()));
        feedback.hidden = true;
      }
    } catch {
      message.textContent = "Could not load the documentation. Check your connection and retry, or use the links below.";
      retry.hidden = false;
    } finally {
      loading = false;
    }
  }
  retry.addEventListener("click", load);
  load();
})();
