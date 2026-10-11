# Product, ownership, and production audit

Date: 2026-10-11. This report records the audit and supersedes the previous report. At audit completion, changes were local and uncommitted; nothing had been pushed, published, or deployed. The user subsequently authorized committing and pushing these changes, as recorded below.

## A. Verified identity and baseline

**AI Inference Layer** is the repository/product name; **Inference** is its existing web workbench name. **AI Inference Server** remains the existing reference API schema title and implementation name. No product was renamed. The product serves developers registering models, testing deterministic classification/generation/embedding engines, and inspecting stored inference results. Python/FastAPI is the reference implementation, with independent TypeScript/Fastify, Go/chi, and Rust/axum ports sharing the core HTTP contract.

The website uses native HTML/CSS/JavaScript, self-hosted fonts, and shared Python-rendered fragments. npm manages browser/deployment tools; uv manages Python; a Python script produces the static website. There is no account authentication UI, dashboard, billing, team management, or frontend framework to redesign. Optional API-key authentication, bounded memory/SQLite/PostgreSQL stores, pagination, batch inference, SSE, and operational probes already exist.

The initial working tree was clean on `main`, at `4c4985a`. Its previous commit already supplied a substantial design system, all three page layouts, and browser tests. This audit preserves that work, refines every existing page through shared components and route-specific copy, closes production build gaps, and fixes actual interaction bugs. It does not claim the existing redesign was newly created in this turn.

Baseline Python: 337 passed, seven skipped; Ruff and mypy passed. TypeScript: 24 tests/typecheck passed. Go: build and race tests passed. Rust: release build and 23 tests passed. The initial browser run passed nine of ten tests; the rendered ReDoc page's combined four-viewport audit exceeded its 45-second test budget. Viewport cases were split into independent tests without removing checks or increasing the timeout.

## B. Design system and shared experience

Direction: compact technical workbench, blue ink, cool neutral surfaces, deliberate IBM Plex typography, and a navy response panel. Existing centralized tokens were retained and extended for read-only controls and the branded 404 layout. A light interface with dark code panels remains intentional; no theme switch or unsupported dark appearance was introduced.

| Role | HEX |
| --- | --- |
| Brand, focus, information | `#2455CF` |
| Hover, subtle brand | `#1B43A7`, `#E9EFFF` |
| Secondary, accent | `#314865`, `#197075` |
| Page, surface, muted surface | `#F4F7FB`, `#FFFFFF`, `#EAF0F8` |
| Primary, secondary, muted text | `#182840`, `#506079`, `#63728A` |
| Border, control border | `#CCD5E2`, `#8291A6` |
| Success, warning, error | `#17623D`, `#805000`, `#B22A35` |
| Code background, text | `#182840`, `#E5EDFA` |

IBM Plex Sans 400/600 handles interface/prose; IBM Plex Mono 400 handles requests and commands. Three local WOFF2 files use `font-display: swap` and system fallbacks. Type sizes: 0.75, 0.875, 1, 1.125, 1.5rem, with fluid 2.5–3.75rem display type. Layout uses a 0.25rem spacing unit, 72rem content width, fluid 1–3rem gutters, 0.25/0.5/0.75rem radii, 2.75rem controls, 3px focus outlines, and 140ms transitions with reduced-motion support. See `brand.md` and `src/static/styles.css` for full tokens.

The shared header now indicates selected homepage anchors and the documentation area, including ReDoc and directory/index URLs. Existing wrapping mobile navigation remains usable. The footer consistently identifies Alisha Karma as maintainer and provides the supplied website, GitHub, X, and contact email. Existing reference/operation links remain real. Documentation intro text distinguishes live mutation-capable Swagger from read-only ReDoc. Open Graph and summary-card metadata were added without guessing a canonical domain or introducing unrelated assets.

## C. Route inventory and completion

| Route | Purpose | Design updated | Functionality tested | Responsive check | Status |
| --- | --- | --- | --- | --- | --- |
| `/` | Product overview, playground, engines, quickstart | Shared shell, metadata, request states | Real three-engine inference, stored history, deleted-model recovery, validation, clipboard, credentials, failures | 320, 375, 390, 430, 768, 1024, 1440, 1600px | Inspected; implemented; tested; verified locally |
| `/docs` | Interactive Swagger API | Shared shell, contextual copy, active navigation, production output | Real schema, authenticated requests, operation permalink, loader retry | 320, 390, 768, 1440px | Inspected; implemented; tested; verified locally |
| `/redoc` | Read-only schema reference | Shared shell, contextual copy, active navigation, production output | Real schema/viewer rendering and view navigation | 320, 390, 768, 1440px | Inspected; implemented; tested; verified locally |
| Unmatched browser GETs, tested as `/missing-page` | 404 recovery | Branded shared-shell page | HTTP 404, recovery navigation, JSON API errors retained | 320, 390, 768, 1440, 1600px | Implemented; tested; verified locally |
| `/docs/oauth2-redirect` | Framework OAuth callback transport | Original framework output retained | HTTP response covered by Python tests; hosting proxy preserved | Not a user-facing layout | Inspected; callback execution not exercised |

API/model/probe/schema/metrics endpoints are machine interfaces, not additional website pages. All existing endpoint contracts remain in place; the Python suite exercises the backend workflows. No nonexistent marketing, legal, login, settings, or account pages were added.

The request input and API key become read-only during submission; credentials are captured once for the multi-request operation. Clipboard reset now respects the response panel's current loading/error state. Both bugs have browser regression coverage. The 404 responds with HTML for browser navigation and retains JSON errors for machine clients, model routes, and missing assets.

The static build now generates `/`, Swagger, ReDoc, and `404.html` from the same renderer as FastAPI. Local documentation rewrites replace the remote page proxies, so page and asset versions are built together. API and OAuth callback proxy destinations remain on the existing backend. A build regression test checks generated assets/templates and rewrite destinations; a browser test exercises actual built pages using a local static host and real API responses through an explicitly simulated hosting rewrite. Actual Vercel routing is not claimed verified by that simulation.

## D. Ownership and originality

GitHub's read-only repository metadata confirmed public ownership by `codealisha99`; description and topics are empty. No remote repository settings changed. Primary maintainership is documented in README/CONTRIBUTING and `.github/CODEOWNERS`. Website credits say "Maintained by" instead of suggesting exclusive creation of all historical work. Existing package author records, historical contributors, timestamps, and third-party/font licenses remain intact. Git configuration belongs to another local identity and was inspected but not modified; no future commit was authorized.

Python, TypeScript, and Rust package homepages now point to the product repository instead of the maintainer's portfolio. TypeScript/Rust repository metadata was added. Documentation explains the relationship between the product and web workbench names and the engines' deterministic limitations.

No unrelated template company, fake customer, testimonial, or placeholder marketing artifact was found in the tracked application. Swagger/ReDoc/service and dependency branding is legitimate and preserved. Test fixture domains/emails are intentional test data. Local environment files are ignored and were not printed or committed. Git history remains unchanged.

## E. Engineering and security

Important changes: `src/web.py`, `src/server.py` (HTML 404 only), static HTML/JS/CSS fragments, `scripts/build_frontend.py`, `vercel.json`, browser/build regression tests, CI, package metadata, maintainer docs, and PostgreSQL connection lifecycle recovery. No schema, migration, business algorithm, production data, or authentication policy changed. No UI runtime dependency was added and no tests were disabled.

The production audit identified a closed PostgreSQL connection being reused indefinitely after an SSL disconnect. `PostgresStore` now reconnects under its existing lock before a subsequent operation, without replaying failed queries or writes. Explicit store shutdown remains closed. Three new integration tests cover persisted history after reconnect, a real server-terminated session followed by API recovery, and shutdown. All eleven PostgreSQL tests pass on an isolated local UTF-8 database. The first disposable cluster defaulted to SQL_ASCII and caused byte/string decoding failures; creating a UTF-8 test database corrected the fixture, without weakening tests or changing production configuration.

The TypeScript dependency audit initially reported ten affected packages (seven high, two moderate, one low). Compatible `npm audit fix` updates plus `npm update tsx` updated the lockfile, including Fastify 5.12.5, Vitest 4.1.11, tsx 4.23.15, and esbuild 0.28.2. Final npm audits report zero advisories for both npm workspaces. Python's installed environment was checked with pip-audit: no known dependency advisories; the unpublished local project itself cannot be audited against PyPI. These results are dependency checks, not a security certification.

The new website CI job builds, tests static routing, and runs real-browser workflow/accessibility tests using isolated local servers. Dependabot now includes root npm tooling. The CI commands were checked locally; the new hosted GitHub job has not run. Existing meaningful architectural/security comments and third-party notices remain; no indiscriminate comment or dependency removal was performed.

## F. Verification evidence

Commands executed (paths relative to the repository):

- `npm run build`: generated all four HTML outputs and shared versioned assets.
- `npm run test:ui`: 19 browser tests passed, including workflows, responsive/accessibility checks, and actual built output. The final runner process ended before its last output could be retrieved after the session resumed; Playwright's last-run artifact confirmed `passed` with no failed tests. The final copy correction also received a targeted responsive/accessibility rerun.
- `node --check` on `app.js`, `shell.js`, `docs.js`: passed.
- Python: `uv run ruff check src tests ../tests/test_frontend_build.py`, `uv run ruff format --check src tests ../tests/test_frontend_build.py`, `uv run mypy`: passed (35 formatted files; 17 typed source files).
- Python: `TEST_DATABASE_URL=postgresql://audit@127.0.0.1:55439/inference_audit uv run python -m pytest --cov --cov-report=term-missing -q`: final result 348 passed, no skips; coverage 98.21%, above the existing 90% threshold. The database is a disposable local PostgreSQL 18 cluster, not the production database; it was stopped after verification. The earlier run without a database passed 338 tests and skipped seven.
- Python: `uv run python -m pytest ../tests/test_frontend_build.py -q`: one passed.
- TypeScript: `npm run typecheck`, `npm test`: passed after updates, 24 tests.
- Go: `go build ./...`, `go test -race ./...`: passed.
- Rust: `cargo build --release`, `cargo test`: passed, 23 integration tests.
- Root and TypeScript: `npm audit --json`: zero advisories after updates.
- `uvx pip-audit --path ai-inference-server-py/.venv/lib/python3.12/site-packages --format=json`: no known dependency advisories, local package excluded.
- `uv sync --directory ai-inference-server-py --extra dev --locked --dry-run`: no environment changes needed.
- `railway status --json` and bounded `railway logs --service api --environment production --lines 80 --json`: read-only diagnosis; log messages were classified without printing secrets. Public `/livez`, `/health`, and `/readyz` were probed without mutating models/data.
- `git diff --check`: passed; final diff reviewed.

Automated WCAG A/AA checks report zero violations in the checked rendered states. Desktop/tablet/mobile screenshots were visually inspected for all three layouts and the 404; screenshots are in ignored `test-results/`. Keyboard/clipboard/reduced-motion, live API-key protection, network failure/retry, loading, and response state behavior are covered. Browser checks use Chrome; they do not establish full accessibility conformance or Safari/Firefox behavior. The collaborative T3 preview explicitly reported no automation host; local Playwright was used after that error.

Read-only public production probes: website `/` and Railway `/livez` returned 200; website `/health` and Railway `/readyz` returned 503 with storage errors. Railway status confirmed the existing `4c4985a` deployment was successful and its instance running. Read-only deployment logs showed an SSL connection closure followed by repeated "connection is closed" errors; the code held that failed connection permanently. This pre-existing outage is a release blocker. The local reconnection fix is verified but remains undeployed; its effect on the live environment is unverified. The original cause of the SSL disconnect remains unknown. No production model/database mutations, secret-variable reads, restart, configuration change, or deployment occurred.

## G. Remaining work and scope limits

- Restore the live API only after approval for release/runtime changes. The local reconnection fix addresses the observed failure mode; the root trigger for the SSL disconnect and live recovery need verification. Do not treat the live playground as healthy merely because the static homepage loads.
- PostgreSQL tests now run against a dedicated disposable local database. Future runs require their own `TEST_DATABASE_URL`; do not use the production database.
- Two pre-existing Starlette/httpx/AnyIO deprecation warnings remain.
- Documentation still uses pinned external viewer bundles; recovery from an unavailable CDN is tested.
- New GitHub CI needs its first hosted run. Docker/container builds and Firefox/Safari/manual screen-reader verification were not run in this turn.
- Remote description/topics are blank; proposed metadata can be applied separately. No Git identity, remote, repository permission, commit, push, publication, or deployment changed.
- No project-wide LICENSE file was found (the font licenses remain present). Unsupported "open-source" claims were replaced with "reference API" copy; a project license requires the maintainer's choice and appropriate rights review.

## Subsequent commit and push authorization

After reviewing the audit, the user explicitly requested a commit and push. The repository-local Git identity was set to Alisha Karma using the authenticated `codealisha99` account's existing GitHub-issued noreply address, verified against the account ID and public commit attribution. Historical commits remain unchanged. The destination is the existing `origin/main`; connected hosting may automatically deploy after the push. No manual deployment, restart, production-data modification, or infrastructure change was requested or performed.
