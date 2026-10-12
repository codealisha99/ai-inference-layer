# Inference design system

Inference is the web workbench for AI Inference Layer's model registry and deterministic inference API. Its interface prioritizes a readable request, an inspectable response, and honest operational status. Alisha Karma appears as the maintainer, with the supplied personal website, GitHub, X, and contact links. Historical contributors remain credited in Git history.

The visual direction is restrained technical clarity: blue ink, cool neutral surfaces, local typography, compact layouts, and a dark response panel. No fabricated social proof, decorative gradients, or account features.

## Logo and brand assets

The convergence mark connects three input nodes to a single output arrow. It
represents the three reference engines behind one API contract, rather than a
generic processor or an unrelated AI symbol. The Inference wordmark uses outlined
IBM Plex Sans Semibold letterforms from the bundled, licensed font.

Assets live in `ai-inference-server-py/src/static/`:

- `favicon.svg`: 32px mark, also suitable as a standalone app icon.
- `logo.svg`: transparent light-surface wordmark used by the shared header and footer.
- `logo-inverse.svg`: white wordmark for dark surfaces.
- `social-card.svg`: editable 1200×630 vector social artwork.
- `social-preview.png`: 1200×630 export referenced by Open Graph and large summary cards.

Keep the mark's proportions intact, leave at least one input node's diameter as
clear space around it, and retain the high-contrast blue/white treatment at small
sizes. Use the supplied inverse lockup on dark surfaces. Product branding should
say Inference; maintainer attribution belongs in credits and contact information.

Regenerate the standalone SVG exports with `uv run scripts/build_brand_assets.py`.
The script's pinned font tooling runs in an isolated environment and is not an
application dependency. After editing the social artwork, export `social-card.svg`
at exactly 1200×630 pixels to refresh `social-preview.png`. Font copyright/OFL
notices remain in `src/static/fonts/`; no project-wide license is implied.

## Palette

| Role | HEX |
| --- | --- |
| Brand / links / focus / information | `#2455CF` |
| Brand hover / subtle background | `#1B43A7` / `#E9EFFF` |
| Secondary / accent | `#314865` / `#197075` |
| Page / surface / muted surface | `#F4F7FB` / `#FFFFFF` / `#EAF0F8` |
| Primary / secondary / muted text | `#182840` / `#506079` / `#63728A` |
| Border / control border | `#CCD5E2` / `#8291A6` |
| Success / background | `#17623D` / `#E6F3EB` |
| Warning / background | `#805000` / `#FFF2D6` |
| Error / background | `#B22A35` / `#FFF0F1` |
| Code background / text / muted / border | `#182840` / `#E5EDFA` / `#B3C2DB` / `#3D506F` |
| Code success / error | `#94D6B4` / `#FFB8BD` |

## Typography and layout

Self-hosted IBM Plex Sans (400, 600) for interface and prose; IBM Plex Mono (400) for requests, responses, and commands. Three Latin WOFF2 files, `font-display: swap`, system fallbacks, and retained font licenses. No runtime font service.

The CSS `:root` in `ai-inference-server-py/src/static/styles.css` is the source of truth. It defines a 0.25rem spacing unit, a 72rem content width, fluid gutters, 0.75–1.5rem interface type sizes, fluid display type, 0.25/0.5/0.75rem radii, 2.75rem controls, a 3px focus outline, and 140ms transitions. Reduced-motion preferences remove transitions and smooth scrolling.

Shared header/footer templates are rendered for the playground, Swagger, and ReDoc. Shared elements include primary/quiet/copy buttons, inputs, engine radios, status badges, output panels, feedback, links, and focus states. Documentation overrides reuse semantic tokens and leave the actual API schema intact.

## Content and interaction rules

Use the product name Inference. Explain that reference engines are deterministic; never imply a hosted LLM or fabricated model quality. Show real server status and real outputs. Input is saved in inference history, disclosed next to the form. API keys stay in the current page only. Provide actionable errors, keyboard navigation, concise live announcements, and focusable code samples. Public references and operational endpoints are real; omit nonexistent legal, support, and account pages.
