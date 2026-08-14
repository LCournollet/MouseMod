"""Generate assets/mousemod.ico from the same glyph the UI draws.

Run: python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path("h:/MouseMod/assets/mousemod.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]

BACKGROUND = (22, 26, 33, 255)
BORDER = (50, 57, 69, 255)
BODY = (232, 234, 237, 255)
ACCENT = (91, 141, 239, 255)


def render(size: int) -> Image.Image:
    """Draw at 4x and downsample, so small sizes stay clean."""
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    unit = canvas / 32

    radius = canvas * 0.22
    draw.rounded_rectangle([0, 0, canvas - 1, canvas - 1], radius=radius,
                           fill=BACKGROUND, outline=BORDER,
                           width=max(1, int(unit * 0.35)))

    # Mouse silhouette
    draw.rounded_rectangle(
        [9 * unit, 4.5 * unit, 23 * unit, 27.5 * unit],
        radius=7 * unit,
        fill=BODY,
    )

    # Scroll wheel
    draw.rounded_rectangle(
        [15.0 * unit, 9 * unit, 17.4 * unit, 15 * unit],
        radius=1.2 * unit,
        fill=ACCENT,
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [render(size) for size in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, sizes {SIZES})")

    preview = Path("h:/MouseMod/assets/icon-preview.png")
    render(256).save(preview)
    print(f"wrote {preview}")


if __name__ == "__main__":
    main()
