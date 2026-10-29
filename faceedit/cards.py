"""The hook title overlay and the end card, drawn as PNGs in brand type."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import ASSETS, FONTS

GREEN, STONE, CREAM, CLAY = "#3A5240", "#6B6157", "#FBF4E8", "#C86B43"
FONT_FILES = {
    "Fraunces SemiBold": "Fraunces-SemiBold.ttf",
    "Nunito Sans ExtraBold": "NunitoSans-ExtraBold.ttf",
    "Nunito Sans SemiBold": "NunitoSans-SemiBold.ttf",
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / FONT_FILES[name]), size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def title_png(text: str, cfg: dict, width: int, height: int, out: Path) -> Path:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = _font(cfg["font"], cfg["size"])
    max_w = width - 260
    lines = _wrap(d, text, font, max_w)
    # Balance the lines: shrink the width while the line count stays the same.
    while max_w > 200 and len(_wrap(d, text, font, max_w - 20)) == len(lines):
        max_w -= 20
    lines = _wrap(d, text, font, max_w)
    asc, desc = font.getmetrics()
    line_h = int((asc + desc) * 1.05)
    box_w = int(max(d.textlength(l, font=font) for l in lines)) + 96
    box_h = line_h * len(lines) + 64
    x0, y0 = (width - box_w) // 2, cfg["top"]
    d.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=36, fill=cfg["box_color"])
    d.rectangle([width // 2 - 40, y0 + box_h - 14, width // 2 + 40, y0 + box_h - 8], fill=CLAY)
    for i, line in enumerate(lines):
        lw = d.textlength(line, font=font)
        d.text(((width - lw) / 2, y0 + 30 + i * line_h), line, font=font, fill=cfg["text_color"])
    img.save(out)
    return out


def endcard_png(cfg: dict, width: int, height: int, out: Path) -> Path:
    img = Image.new("RGB", (width, height), CREAM)
    d = ImageDraw.Draw(img)
    mark = Image.open(ASSETS / "mark-full.png").convert("RGBA")
    mw = 560
    mark = mark.resize((mw, int(mark.height * mw / mark.width)), Image.LANCZOS)
    top = int(height * 0.24)
    img.paste(mark, ((width - mw) // 2, top), mark)
    y = top + mark.height + 70

    name_font = _font("Fraunces SemiBold", 92)
    for text, font, color, gap in (
        ("My House Guardian", name_font, GREEN, 26),
        (cfg["tagline"], _font("Fraunces SemiBold", 60), CLAY, 70),
    ):
        tw = d.textlength(text, font=font)
        d.text(((width - tw) / 2, y), text, font=font, fill=color)
        y += sum(font.getmetrics()) + gap
    d.rectangle([width // 2 - 60, y - 30, width // 2 + 60, y - 26], fill="#E8DFCD")
    small = _font("Nunito Sans SemiBold", 52)
    for line in cfg["lines"]:
        tw = d.textlength(line, font=small)
        d.text(((width - tw) / 2, y), line, font=small, fill=STONE)
        y += sum(small.getmetrics()) + 14
    img.save(out)
    return out
