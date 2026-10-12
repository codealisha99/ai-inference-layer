# Ownership, authorship, and brand audit

Date: 2026-10-12. Baseline: clean working tree on `main`, commit `ea11404`.
At audit completion, this round's corrections were local and uncommitted. No history,
remote settings, repository permissions, production data, or deployment was changed.
The user subsequently authorized committing and pushing these files to the existing
`origin/main`. Connected hosting may automatically deploy after that push; no manual
deployment or infrastructure change is part of this authorization.

## Canonical identity and preserved provenance

Primary author and maintainer: **Alisha Karma**, GitHub **codealisha99**.
Profile: https://github.com/codealisha99. Website: https://alishakarma.com.
Public contact: lishykarma99@gmail.com.

AI Inference Layer remains the repository/API project name; Inference remains the
web workbench. API implementation/package names remain intact. Package metadata
identifies the primary author, not the exclusive writer of every historical line.

Git history includes the names Alisha Karma, codealisha99, Abhijitam01, T3 Code,
and dependabot[bot]. These historical records were preserved without identity
mapping, rewriting, squashing, or contributor-statistics manipulation. GitHub's
contributors endpoint currently attributes its recognized account contributions
to codealisha99; that does not supersede the local historical author records.

IBM font copyright and OFL notices, dependency licenses, framework/viewer branding,
and meaningful implementation/security comments remain intact. No unrelated
company, fictional author, or template-author attribution was identified that
needed removal. No project-wide LICENSE exists; none was invented or assigned.

## Inspected files and metadata

Reviewed root/Python READMEs, ARCHITECTURE, CHANGELOG, CONTRIBUTING, SECURITY,
DEPLOYMENT, the prior DESIGN_AUDIT, brand guidelines, CODEOWNERS, all four language
manifests plus root npm manifests/lockfiles, Dockerfiles, Makefile, deployment
configuration, GitHub CI/Dependabot, shared HTML/JS/CSS assets, API contact metadata,
font licenses, tests, Git configuration/history/branch/remotes, and accessible
GitHub repository settings. No About page exists; relevant application credits
are the shared footer and document author metadata. No AUTHORS, CONTRIBUTORS,
mailmap, or project-wide license file exists. Test-only identities are fixtures,
not additional maintainers.

## Changes and reasons

| File(s) | Correction |
| --- | --- |
| `OWNERSHIP.md` | Canonical primary author, contact, maintainer scope, historical attribution, and explicit license status |
| Root `package.json` | Identify the build-tools package's primary author/contact and real repository; package name unchanged |
| `ai-inference-server-ts/package.json` | Add the supplied public author contact alongside existing correct name/website |
| `ai-inference-server-py/pyproject.toml` | Use the public contact for package metadata; keep the Git noreply address for Git commits |
| `ai-inference-server-rust/Cargo.toml` | Replace a website in the angle-bracket email position with the supplied public email |
| Both Dockerfiles | Add OCI product title, primary author/contact, and repository source labels; no license claim or runtime change |
| `README.md` | Show the product logo, document locked uv setup, and link ownership/brand guidance |
| `CONTRIBUTING.md` | Align reproducible setup with the checked-in uv lock and invoke pytest through the project Python |
| `ARCHITECTURE.md` | Correct the product heading, include PostgreSQL/reconnection, distinguish JSON API envelopes from HTML/SSE/metrics, remove the inaccurate dependency-free server claim |
| `DEPLOYMENT.md` | Remove duplicated build wording; keep existing infrastructure and deployment commands intact |
| `SECURITY.md` | Replace an unavailable GitHub reporting path with the canonical private contact, matching the inspected disabled setting; remove an unverified response-time promise |
| `CHANGELOG.md` | Describe actual unreleased work without new contributors, artificial releases, or invented dates/metrics |
| `Makefile` | Use the selected Python for Ruff/mypy/pytest and include the same formatting check as CI |
| `src/static/favicon.svg` | Replace generic processor geometry with the Inference convergence mark |
| `src/static/logo.svg`, `logo-inverse.svg` | Standalone, outlined wordmarks for light/dark surfaces |
| `src/static/social-card.svg`, `social-preview.png` | Vector source and 1200×630 PNG social asset using actual product/maintainer copy |
| `src/static/header.html`, `footer.html` | Use one shared product lockup while preserving accessible link names and canonical maintainer attribution |
| `src/static/index.html`, `docs.html` | Reference the real social asset and large summary card; remove a duplicate, unused font preload from the homepage |
| `scripts/build_brand_assets.py` | Reproducible standalone vector exports using bundled font files and isolated, pinned fonttools/Brotli tooling |
| `brand.md` | Document logo meaning, assets, contrast/clear space, typography, regeneration, and appropriate product-versus-maintainer branding |
| `OWNERSHIP_AUDIT.md` | Record this round's findings, actual changes, checks, and limits |

The existing correct CODEOWNERS, Python README maintainer attribution, API contact
name/URL, and HTML author name were inspected and preserved. No application
business logic, authentication, schema, dependency versions, or lockfiles changed.
Optional artwork tooling runs outside the application's dependency environment.

## Logo and brand direction

Three inputs converge into one output, representing the three deterministic engines
behind a shared contract. The wordmark is Inference, not the maintainer's name.
Brand blue `#2455CF`, navy `#182840`, and paper `#F4F7FB` remain the existing palette.
Outlined IBM Plex Sans letterforms remove runtime font dependencies from exported
SVGs. Font notices are retained. The social PNG was exported at 1200×630 through
the collaborative browser's canvas using the actual standalone vector source.

## Git identity and GitHub settings

- Repository owner: codealisha99; visibility: public; default branch: main.
- Repository description: empty; topics: empty; no published releases returned.
- Classic branch protection endpoint reports main unprotected; effective branch
  rules endpoint returns an empty array.
- GitHub private vulnerability reporting: disabled.
- Previous committed audit's CI run completed successfully:
  https://github.com/codealisha99/ai-inference-layer/actions/runs/38141164044.
- Git identity is already configured locally as Alisha Karma. The configured
  GitHub-issued noreply address matches the authenticated account ID and its public
  commit attribution. The account email-settings endpoint was inaccessible; no
  private account email was printed or guessed. Git configuration was not changed.
- Existing `origin` remains https://github.com/codealisha99/ai-inference-layer.git.

Proposed remote description: "Model registry and deterministic inference API in
Python, TypeScript, Go, and Rust, with a developer playground."
Proposed topics: `model-registry`, `inference-api`, `developer-tools`, `fastapi`,
`python`, `typescript`, `golang`, `rust`.
These are proposals only. Enabling private reporting and branch protections, or
choosing a project license, requires a separate maintainer decision; none was applied.

## Checks actually executed

- Baseline Ruff/mypy, static build, and 41 Python landing/hardening tests: passed.
- `uv run scripts/build_brand_assets.py`: passed. Font tooling versions were
  checked against PyPI; pinned fonttools 4.66.1 and Brotli 1.2.0 reproduce the same SVG exports.
- `npm run build`: passed, including the new shared logo/social assets.
- `npm run test:ui`: **19 passed**. Real inference, credentials, recovery, clipboard,
  Swagger requests, ReDoc, static output, reduced motion, browser 404, and responsive
  WCAG checks remained functional. Checked homepage widths 320–1600px; documentation
  widths 320/390/768/1440px. No automated WCAG violations in the checked states.
- Python: Ruff lint/format and mypy passed. `uv run python -m pytest --cov -q`:
  **338 passed, 10 skipped**, **92.93% coverage** (90% threshold).
- Python static build regression test: **1 passed**.
- Final OpenAPI/hardening tests: **57 passed**. API contact behavior was preserved
  without adding an optional runtime email-validator dependency.
- TypeScript: typecheck passed; **24 tests passed**.
- Rust: `cargo metadata --no-deps --format-version 1` and `cargo check` passed.
- npm audits in root and TypeScript workspaces: **zero advisories**.
- `uv sync --directory ai-inference-server-py --extra dev --locked --dry-run`:
  no environment changes required.
- `git diff --check`: passed; final diff and asset references inspected.
- Collaborative browser: desktop logo/page inspected; both logos loaded at 320px
  without page overflow. The host later disconnected, so further manual interaction
  was unavailable; the repository's complete browser suite passed independently.

## Remaining limitations and preserved state

Ten PostgreSQL tests were skipped without a dedicated test database in this round;
no PostgreSQL code changed. The preceding audit verified the full database suite,
but this report does not count those checks as freshly rerun. Existing
Starlette/httpx/AnyIO deprecation warnings remain. Docker images and untouched Go
code were not rebuilt/retested in this round. Browser checks cover Chrome, not
Safari/Firefox or a complete screen-reader audit. Social preview metadata references
the configured product domain; these new assets have not been published or uploaded
to GitHub repository settings. No live production health claim is made here.

The initial tree was clean. All changes in this round belong to the audit and logo
work. Existing history, contributor identities, licenses, branch/remotes, and user
configuration were preserved. During the audit, no commit, push, deployment,
repository transfer, visibility/permission change, or message to another person
was performed. The subsequent commit/push is explicitly authorized by the user.
