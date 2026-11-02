#!/usr/bin/env python3
"""Makes a 9:16 Instagram Story card for each new blog post on myhouseguardian.com.

New posts are found by reading the site's sitemap and comparing it with
stories/blog/seen.json. Each new post gets stories/blog/<slug>.jpg: the post's
title and summary in brand type, with a "Read it here" arrow and empty space
below it for a link sticker. Andrew posts the card by hand from his phone and
adds the sticker (the API can't add link stickers), so these cards never enter
the auto rotation: the poster only reads JPEGs at the top of stories/ and in
stories/once/.

Usage:
  python tools/blog_story.py              # make cards for new posts, record them as seen
  python tools/blog_story.py --dry-run    # list new posts, write nothing
  python tools/blog_story.py --url <post> # (re)make the card for one post, seen or not
  python tools/blog_story.py --seed       # mark every current post as seen, make no cards

Needs Pillow (already in the faceedit venv).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "stories" / "blog"
SEEN = OUT_DIR / "seen.json"
ASSETS = ROOT / "faceedit" / "assets"
FONTS = ASSETS / "fonts"
SITEMAP = "https://myhouseguardian.com/sitemap.xml"

GREEN, CLAY, CREAM, STONE = "#3A5240", "#C86B43", "#FBF4E8", "#6B6157"
W, H = 1080, 1920
SIDE = 110
TEXT_BOTTOM = 1360  # title and summary end above this
HINT_Y = 1430       # "Read it here" arrow; 1500-1680 stays empty for the sticker


def fetch(url: str, tries: int = 3) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "mhg-blog-story/1"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(5)
    raise AssertionError("unreachable")


def blog_urls() -> list[str]:
    """Blog posts are the sitemap pages nested under a section, e.g. /fairfield/<post>."""
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", fetch(SITEMAP))
    return [u for u in urls if len([s for s in urllib.parse.urlparse(u).path.split("/") if s]) >= 2]


def meta(page: str, prop: str) -> str:
    m = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"', page)
    return html.unescape(m.group(1)).strip() if m else ""


def post_info(url: str) -> dict:
    page = fetch(url)
    title = meta(page, "og:title")
    if not title:
        m = re.search(r"<title>([^<]*)", page)
        title = html.unescape(m.group(1)) if m else url
    title = re.sub(r"\s*\|\s*My House Guardian\s*$", "", title).strip()
    return {"url": url, "title": title, "description": meta(page, "og:description")}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def wrap(d: ImageDraw.ImageDraw, text: str, f, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def layout(d, info: dict, max_w: int, ts: int, ds: int):
    """Fonts and lines for the title and summary at these sizes, plus the block's height."""
    tf = font("Fraunces-SemiBold.ttf", ts)
    df = font("NunitoSans-SemiBold.ttf", ds)
    tlines = wrap(d, info["title"], tf, max_w)
    dlines = wrap(d, info["description"], df, max_w) if info["description"] else []
    th, dh = int(sum(tf.getmetrics()) * 1.08), int(sum(df.getmetrics()) * 1.15)
    height = th * len(tlines) + 40 + 6 + 76 + dh * len(dlines)
    return tf, tlines, th, df, dlines, dh, height


def centered(d, y: int, text: str, f, fill: str) -> None:
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def render(info: dict, out: Path) -> Path:
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    max_w = W - 2 * SIDE

    # Instagram's own header covers roughly the top 220px; start below it.
    mark = Image.open(ASSETS / "mark-full.png").convert("RGBA")
    mw = 260
    mark = mark.resize((mw, int(mark.height * mw / mark.width)), Image.LANCZOS)
    y = 250
    img.paste(mark, ((W - mw) // 2, y), mark)
    y += mark.height + 60

    label = font("NunitoSans-ExtraBold.ttf", 44)
    centered(d, y, "New on the blog", label, CLAY)
    y += sum(label.getmetrics()) + 44

    # Shrink the title (and the summary with it) until the block ends above TEXT_BOTTOM.
    for ts in range(100, 51, -4):
        tf, tlines, th, df, dlines, dh, height = layout(d, info, max_w, ts, max(32, min(46, ts // 2)))
        if y + height <= TEXT_BOTTOM:
            break
    for line in tlines:
        centered(d, y, line, tf, GREEN)
        y += th
    y += 40
    d.rectangle([W // 2 - 60, y, W // 2 + 60, y + 6], fill=CLAY)
    y += 76
    for line in dlines:
        centered(d, y, line, df, STONE)
        y += dh

    centered(d, HINT_Y, "Read it here", font("NunitoSans-SemiBold.ttf", 40), STONE)
    # A down arrow, drawn (the brand fonts have no arrow glyph).
    ax, ay = W // 2, HINT_Y + 72
    d.line([ax, ay, ax, ay + 34], fill=CLAY, width=5)
    d.line([ax - 16, ay + 18, ax, ay + 36, ax + 16, ay + 18], fill=CLAY, width=5, joint="curve")
    img.save(out, "JPEG", quality=92)
    return out


def slug(url: str) -> str:
    return urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--url")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else []

    if args.url:
        out = render(post_info(args.url), OUT_DIR / f"{slug(args.url)}.jpg")
        print(f"[card] {out.relative_to(ROOT)}  <- {args.url}")
        return 0

    new = [u for u in blog_urls() if u not in seen]
    if not new:
        print("No new blog posts.")
        return 0
    for u in new:
        if args.dry_run:
            print(f"[new] {u}")
        elif args.seed:
            print(f"[seen] {u}")
        else:
            info = post_info(u)
            out = render(info, OUT_DIR / f"{slug(u)}.jpg")
            print(f"[card] {out.relative_to(ROOT)}  <- {info['title']}  ({u})")
    if not args.dry_run:
        SEEN.write_text(json.dumps(seen + new, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
