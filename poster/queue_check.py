#!/usr/bin/env python3
"""Checks every post in queue/ against Instagram's rules before anything is sent.

Run it any time:  python poster/queue_check.py
It also runs on every push, so a bad post fails in GitHub instead of at 9am.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "queue"

MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_CAROUSEL = 20
MAX_BYTES = 8 * 1024 * 1024
# Instagram feed images must fall between 4:5 (tall) and 1.91:1 (wide).
MIN_RATIO, MAX_RATIO = 4 / 5, 1.91


def load_post(folder: Path) -> dict:
    return json.loads((folder / "post.json").read_text())


def jpeg_size(path: Path) -> tuple[int, int] | None:
    """Width and height of a baseline or progressive JPEG, or None if it is not a JPEG."""
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg_len
    return None


def check_post(folder: Path) -> list[str]:
    problems: list[str] = []
    pj = folder / "post.json"
    if not pj.exists():
        return ["missing post.json"]
    try:
        post = load_post(folder)
    except ValueError as e:
        return [f"post.json is not valid JSON ({e})"]

    when = post.get("publish_at", "")
    try:
        t = dt.datetime.fromisoformat(when)
        if t.tzinfo is None:
            problems.append("publish_at needs a time zone, e.g. 2026-10-27T09:00:00-04:00")
    except (TypeError, ValueError):
        problems.append("publish_at is missing or not a date like 2026-10-27T09:00:00-04:00")

    caption = post.get("caption", "")
    if not isinstance(caption, str) or not caption.strip():
        problems.append("caption is empty")
    elif len(caption) > MAX_CAPTION:
        problems.append(f"caption is {len(caption)} characters (max {MAX_CAPTION})")
    elif len(re.findall(r"#\w+", caption)) > MAX_HASHTAGS:
        problems.append(f"more than {MAX_HASHTAGS} hashtags")

    images = post.get("images", [])
    if not images:
        problems.append("no images listed")
    if len(images) > MAX_CAROUSEL:
        problems.append(f"{len(images)} images (carousel max {MAX_CAROUSEL})")
    ratios = set()
    for name in images:
        p = folder / name
        if not p.exists():
            problems.append(f"{name} not found")
            continue
        if p.stat().st_size > MAX_BYTES:
            problems.append(f"{name} is over 8 MB")
        size = jpeg_size(p)
        if size is None:
            problems.append(f"{name} is not a JPEG (Instagram's API only accepts JPEG)")
            continue
        w, h = size
        r = w / h
        if r < MIN_RATIO - 0.01 or r > MAX_RATIO + 0.01:
            problems.append(f"{name} is {w}x{h}; ratio must be between 4:5 and 1.91:1")
        ratios.add(round(r, 3))
    if len(ratios) > 1:
        problems.append("carousel images have different shapes; Instagram crops them all to the first one")
    return problems


def main() -> int:
    if not QUEUE_DIR.exists():
        print("queue/ is empty")
        return 0
    bad = 0
    for folder in sorted(p for p in QUEUE_DIR.iterdir() if p.is_dir()):
        problems = check_post(folder)
        done = (folder / "result.json").exists()
        tag = "done" if done else ("ok" if not problems else "FIX")
        print(f"[{tag}] {folder.name}" + ("" if not problems else ": " + "; ".join(problems)))
        if problems and not done:
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
