# Website redesign and production audit

Date: 2026-10-11. Scope: the Python reference server's website and its Vercel static build. Verification was performed locally before publication. No cloud deployment was performed during the redesign audit itself.

## Product and baseline

The product is Inference, a model registry and inference API with deterministic classification, generation, and embedding engines. Users are developers evaluating the API, integrating it, and inspecting inference history. The site uses native HTML, CSS, and JavaScript, served by FastAPI; there is no frontend framework or UI component library. Python dependencies use uv, deployment/browser tooling uses npm, and static production output uses a small Python build script. Other language ports remain unchanged.

Git was clean at the start. Baseline Python results were 333 passed, 7 skipped. Baseline lint and type checks passed. Problems included inconsistent typography/spacing, a separate unbranded documentation experience, hidden API-key recovery, weak clipboard failure feedback, limited responsive state verification, and no browser regression suite. The engines already returned deterministic reference outputs; the new copy states that plainly.

## Branding and system

The chosen direction is a compact developer workbench: blue ink, cool neutral surfaces, readable local typography, and a navy JSON response panel. Product identity stays Inference. The supplied Alisha Karma website, GitHub, and X links appear in creator attribution; no contact email, fictitious legal pages, metrics, testimonials, credentials, or account features were added.

See `brand.md` for the complete HEX palette, typography, spacing, and interaction rules. `styles.css` centralizes semantic colors, type sizes, spacing, dimensions, radii, borders, focus, layering, and motion. Self-hosted IBM Plex Sans 400/600 and IBM Plex Mono 400 use three WOFF2 files with retained licenses and system fallbacks.

## Pages, routes, and components

- `/`: complete landing/playground redesign, real three-engine outputs, copyable JSON and setup commands, visible request endpoint, honest descriptions, input validation, loading feedback, API-key disclosure/recovery, and actionable network/rate-limit errors.
- `/docs`: shared branded shell around real Swagger, current-page navigation, memory-only API-key input, interactive request support, readable operation styles, corrected badge/control/response contrast, accessible operation permalinks, and recoverable viewer loading errors.
- `/redoc`: shared shell and token-based real ReDoc theme, readable response tabs, keyboard-focusable code samples, and loading/retry feedback.
- `/docs/oauth2-redirect`: original framework redirect behavior retained.
- `/openapi.json`, `/health`, `/readyz`, `/metrics`: linked real operational/schema endpoints, covered by existing route tests. These are machine-readable outputs, not additional website layouts. Existing `/livez` and model/inference API routes remain intact and are covered by Python tests. There are no account, settings, marketing subpages, or legal routes to redesign.

Header/footer fragments are shared across every HTML layout. Navigation wraps on small screens, has keyboard focus and page indicators, and links to existing sections/routes. The footer includes live operational data, references, and restrained creator attribution. No new backend business rules, API schemas, storage migrations, authentication changes, or integrations were introduced.

The playground transitions from a desktop split layout to stacked mobile panels. Forms retain comfortable controls and mobile input sizing. Long JSON/commands use scrollable, focusable code regions. Native radio controls, visible labels, skip links, validation associations, concise live announcements, disabled/loading states, and reduced-motion behavior support accessibility. Keys never enter browser storage.

## Cleanup and implementation

Replaced scattered styles with semantic tokens and reusable component classes. Removed decorative separator comments and redundant UI scaffolding while rewriting the frontend. Retained comments explaining model registration races, dynamic documentation samples, build inputs, architectural/security logic, required directives, and font licenses. No broad comment deletion or dependency removal occurred.

`src/web.py` renders shared templates and fingerprints local assets. The production build uses the same renderer, preventing drift between FastAPI and Vercel output. HTML template inputs are omitted from built asset output. No new runtime UI dependency was added. `@playwright/test` and `@axe-core/playwright` are development-only dependencies for reproducible real-browser regression and accessibility checks.

## Verification

Commands run from the repository root unless indicated:

- `npm run build`: passed; generated production static output with shared shell and versioned assets.
- `node --check` for `app.js`, `shell.js`, and `docs.js`: passed.
- `git diff --check`: passed.
- In `ai-inference-server-py`: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy`: passed; 34 formatted files and 17 typed source files.
- In `ai-inference-server-py`: `uv run python -m pytest --cov --cov-report=term-missing -q`: 337 passed, 7 skipped; coverage 93.58%, exceeding the existing 90% threshold. Direct `uv run pytest` initially invoked a stale script interpreter and failed import resolution; invoking the module with the project Python corrected the local runner issue without code/test changes.
- `npm run test:ui`: 10 passed in 43.7 seconds; browser regression suite covering real inference for all engines, stored history, deleted-model recovery, validation, keyboard shortcut/focus, successful and denied clipboard access, real API-key protection, network failure/retry, loading states, documentation rendering/CDN failure recovery, interactive Swagger requests, and reduced motion.

To rerun browser checks, install npm dependencies with `npm ci`, sync Python development dependencies with `uv sync --extra dev` in the Python directory, and have Google Chrome installed (the configuration uses its `chrome` channel).

Browser checks use isolated Chrome and two disposable in-memory local servers, with separate public and key-protected configurations. Real API calls are used; controlled network/clipboard failures exercise error handling. No production database or credentials enter these tests. Playground widths: 320, 375, 390, 430, 768, 1024, 1440, 1600px. Documentation widths: 320, 390, 768, 1440px. Automated axe checks target WCAG A/AA and report no violations in checked rendered states; this does not establish complete accessibility conformance. Screenshots are written to ignored `test-results/` and manually reviewed for desktop/mobile hierarchy and layout.

The collaborative preview was explicitly unavailable after connection failures; verification used an isolated local browser. Initial browser audits identified Swagger badge contrast and ReDoc tab contrast/code keyboard access; those issues were fixed. Expanded Swagger checks also found low-contrast controls, response syntax, and nested permalinks; semantic token overrides and separate permalink controls corrected them. A new Swagger test initially needed to expand its collapsed operation group; its selector and query-string response matching were corrected without weakening the assertions.

## Important files

Updated: `src/server.py` (HTML serving only), `src/static/index.html`, `styles.css`, `app.js`, `favicon.svg`, `tests/test_landing.py`, `scripts/build_frontend.py`, root npm manifests, `.gitignore`.

Added: `src/web.py`, shared `header.html`/`footer.html`, `shell.js`, `docs.html`/`docs.css`/`docs.js`, licensed local fonts, `playwright.config.js`, `tests/ui/website.spec.js`, `brand.md`, this report.

## Remaining work and limits

- Seven existing PostgreSQL integration tests were skipped because `TEST_DATABASE_URL` was not supplied. Storage/business logic was not changed; this audit does not claim a fresh PostgreSQL integration run.
- Two existing Starlette/httpx/AnyIO deprecation warnings remain. Tests pass; no unrelated dependency migration was performed.
- Documentation viewers still depend on pinned external CDN bundles; an actual recoverable failure and retry was tested. Fonts and main interface assets are local.
- Browser verification covers Chrome, not Safari/Firefox or a manual screen-reader audit.
- Production deployment health must be verified separately after publication; this report records local application and build verification.
- Installed Vercel CLI 51.8.0 is outdated. Upgrade with `npm i -g vercel@latest` before a future release for compatibility; no global tooling was changed during this task.
