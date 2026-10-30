"""The B-roll review sheet: one image showing every cutaway moment, its candidate
clips side by side (the one in use outlined in clay), and the clips still to film.

Look at it before rendering; swap or drop picks with `faceedit broll <plan> 2=3 1=0`.
"""
from __future__ import annotations

import subprocess
import textwrap
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .broll import UA
from .cards import CLAY, CREAM, FONT_FILES, GREEN, STONE
from .config import FONTS, cache_dir
from .cuts import to_edited

THUMB_W, THUMB_H, PAD = 300, 300, 24


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / FONT_FILES[name]), size)


def _thumb(opt: dict) -> Image.Image | None:
    """A still for one candidate: Pixabay's preview image, or a frame from your clip."""
    d = cache_dir() / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    try:
        if opt.get("source") == "local":
            out = d / (str(abs(hash(opt["file"]))) + ".jpg")
            if not out.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(Path(opt["file"]).expanduser()),
                                "-frames:v", "1", "-vf", "scale=600:-2", str(out)], check=True)
        elif opt.get("thumb"):
            out = d / f"{opt['source']}-{opt.get(opt['source'] + '_id')}.jpg"
            if not out.exists():
                req = urllib.request.Request(opt["thumb"], headers={"User-Agent": UA})
                out.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        else:
            return None
        img = Image.open(out).convert("RGB")
    except Exception:  # a missing preview shouldn't stop the sheet
        return None
    img.thumbnail((THUMB_W, THUMB_H))
    return img


def write_sheet(plan: dict, out: Path) -> Path:
    moments = plan.get("broll", [])
    missing = [line for w in plan.get("broll_missing", []) for line in textwrap.wrap("- " + w, 88, subsequent_indent="  ")]
    head, body, small = _font("Fraunces SemiBold", 40), _font("Nunito Sans SemiBold", 26), _font("Nunito Sans SemiBold", 20)
    row_h = THUMB_H + 90
    width = PAD * 2 + 3 * (THUMB_W + PAD)
    height = 110 + max(1, len(moments)) * row_h + (60 + 34 * len(missing) if missing else 0) + PAD
    sheet = Image.new("RGB", (width, height), CREAM)
    d = ImageDraw.Draw(sheet)
    d.text((PAD, PAD), "B-roll review", font=head, fill=GREEN)
    d.text((PAD, PAD + 52), "Outlined = in use. Stock is only a suggestion until approved: faceedit broll <plan> MOMENT=OPTION",
           font=small, fill=STONE)
    y = 110
    if not moments:
        d.text((PAD, y), "No cutaways in this video.", font=body, fill=STONE)
    for k, m in enumerate(moments, 1):
        t = to_edited(m["at"] + 0.1, plan["segments"]) or 0
        approved = m.get("approved", True)
        d.text((PAD, y), f"{k}.  {int(t // 60)}:{int(t % 60):02d}  \"{m['said']}\"   [{m['search']}]"
               + ("" if approved else "   SUGGESTIONS, none in use"), font=body, fill=GREEN if approved else CLAY)
        options = m.get("options") or [m]
        pick = next((i for i, o in enumerate(options) if (o.get("file") or o.get("download")) in
                     (m.get("file"), m.get("download"))), 0)
        for i, opt in enumerate(options[:3]):
            x = PAD + i * (THUMB_W + PAD)
            box = (x, y + 40, x + THUMB_W, y + 40 + THUMB_H)
            d.rectangle(box, fill="#E8DFCD")
            img = _thumb(opt)
            if img:
                sheet.paste(img, (x + (THUMB_W - img.width) // 2, y + 40 + (THUMB_H - img.height) // 2))
            if i == pick and approved:
                d.rectangle(box, outline=CLAY, width=8)
            label = f"{i + 1}  {'your clip' if opt.get('source') == 'local' else opt.get('source', '')}"
            d.rectangle((x, y + 40, x + 170, y + 74), fill=GREEN)
            d.text((x + 10, y + 43), label, font=small, fill=CREAM)
        y += row_h
    if missing:
        d.text((PAD, y), "Still to film (add to ~/Movies/MHG-broll):", font=body, fill=CLAY)
        y += 44
        for w in missing:
            d.text((PAD, y), w, font=small, fill=STONE)
            y += 34
    sheet.save(out, quality=88)
    return out
