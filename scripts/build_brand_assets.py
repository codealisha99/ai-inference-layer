# /// script
# requires-python = ">=3.12"
# dependencies = ["fonttools==4.66.1", "brotli==1.2.0"]
# ///
"""Export standalone Inference SVG assets from the bundled, licensed IBM Plex fonts."""

from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

STATIC = Path(__file__).resolve().parents[1] / "ai-inference-server-py/src/static"
BRAND = "#2455CF"
INK = "#182840"
PAPER = "#F4F7FB"
WHITE = "#FFFFFF"


def mark() -> str:
    return (
        f'<rect width="32" height="32" rx="7" fill="{BRAND}"/>'
        f'<g fill="none" stroke="{WHITE}" stroke-width="2.25" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8 8h5a4 4 0 0 1 4 4v8a4 4 0 0 1-4 4H8M8 16h17m-4-4 4 4-4 4"/>'
        f'</g><g fill="{WHITE}"><circle cx="8" cy="8" r="2"/>'
        '<circle cx="8" cy="16" r="2"/><circle cx="8" cy="24" r="2"/></g>'
    )


def lettering(font: TTFont, text: str, size: float, x: float, baseline: float) -> str:
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    paths = []
    for char in text:
        glyph = glyphs[cmap[ord(char)]]
        pen = SVGPathPen(glyphs)
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        paths.append(f'<path d="{pen.getCommands()}"/>')
        x += glyph.width * scale
    return "".join(paths)


def export(name: str, width: int, height: int, title: str, body: str) -> None:
    description = (
        "Three input channels converge into one output. "
        "Wordmark outlines use IBM Plex Sans; font copyright and OFL notices are in fonts/."
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">'
        f'<title id="title">{title}</title><desc id="description">{description}</desc>'
        f"{body}</svg>\n"
    )
    (STATIC / name).write_text(svg)


def main() -> None:
    with (
        TTFont(STATIC / "fonts/ibm-plex-sans-latin-600-normal.woff2") as bold,
        TTFont(STATIC / "fonts/ibm-plex-sans-latin-400-normal.woff2") as regular,
    ):
        export("favicon.svg", 32, 32, "Inference mark", mark())
        for name, color in (("logo.svg", INK), ("logo-inverse.svg", WHITE)):
            export(
                name,
                288,
                64,
                "Inference",
                f'<g transform="scale(2)">{mark()}</g>'
                f'<g fill="{color}">{lettering(bold, "Inference", 48, 80, 49)}</g>',
            )
        card = (
            f'<rect width="1200" height="630" fill="{PAPER}"/>'
            f'<g transform="translate(88 72) scale(2)">{mark()}</g>'
            f'<g fill="{INK}">{lettering(bold, "Inference", 48, 168, 121)}</g>'
            f'<path d="M88 184H1112" stroke="#CCD5E2"/>'
            f'<g fill="{INK}">{lettering(bold, "One registry.", 72, 88, 300)}'
            f"{lettering(bold, 'Three ways to infer.', 72, 88, 390)}</g>"
            f'<g transform="translate(912 238) scale(6.25)">{mark()}</g>'
            f'<g fill="#506079">'
            f"{lettering(regular, 'Deterministic engines. Inspectable responses.', 28, 88, 472)}"
            f"{lettering(regular, 'Maintained by Alisha Karma', 22, 88, 558)}</g>"
        )
        export("social-card.svg", 1200, 630, "Inference: one registry, three ways to infer", card)


if __name__ == "__main__":
    main()
