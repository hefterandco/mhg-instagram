#!/usr/bin/env python3
"""Checks every post in queue/ against Instagram's rules before anything is sent.

Run it any time:  python poster/queue_check.py
It also runs on every push, so a bad post fails in GitHub instead of at 9am.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "queue"
STORIES_DIR = ROOT / "stories"
# Reel videos are too big for the repo, so they live on this GitHub Release as <folder>.mp4.
REELS_RELEASE = "reels"
# faceedit writes this as the caption; a post holding it is a draft and never publishes.
CAPTION_PLACEHOLDER = "WRITE THE CAPTION HERE"
LOCAL_TZ = ZoneInfo("America/New_York")

MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_MENTIONS = 20
# Meta's docs say 20, but its error table still says 2-10 (subcode 2207028).
# Stay at 10 until a bigger carousel is proven to post. See docs/RESEARCH.md.
MAX_CAROUSEL = 10
MAX_ALT_TEXT = 1000
MAX_BYTES = 8 * 1024 * 1024
# Instagram feed images must fall between 4:5 (tall) and 1.91:1 (wide).
MIN_RATIO, MAX_RATIO = 4 / 5, 1.91
# Stories should be 9:16 (1080x1920) so nothing gets cropped.
STORY_RATIO = 9 / 16


def load_post(folder: Path) -> dict:
    return json.loads((folder / "post.json").read_text())


def is_draft(folder: Path) -> bool:
    """True while the caption is still faceedit's placeholder."""
    try:
        return CAPTION_PLACEHOLDER in load_post(folder).get("caption", "")
    except (OSError, ValueError, AttributeError):
        return False


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


def repo_slug() -> str:
    """owner/repo, from GitHub Actions or from this clone's remote."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    url = subprocess.run(["git", "-C", str(ROOT), "config", "--get", "remote.origin.url"],
                         capture_output=True, text=True).stdout.strip()
    return re.sub(r"(\.git)?$", "", re.split(r"github\.com[:/]", url)[-1])


def reel_release_url(folder_name: str) -> str:
    return f"https://github.com/{repo_slug()}/releases/download/{REELS_RELEASE}/{folder_name}.mp4"


def check_jpeg(path: Path, label: str) -> tuple[list[str], tuple[int, int] | None]:
    if not path.exists():
        return [f"{label} not found"], None
    problems = []
    if path.stat().st_size > MAX_BYTES:
        problems.append(f"{label} is over 8 MB")
    size = jpeg_size(path)
    if size is None:
        problems.append(f"{label} is not a JPEG (Instagram's API only accepts JPEG)")
    return problems, size


def check_reel(folder: Path, post: dict) -> list[str]:
    problems = []
    if post.get("images"):
        problems.append('a reel uses "reel": true instead of "images"; remove one')
    if post.get("alt_text"):
        problems.append("alt_text doesn't work on reels")
    if not isinstance(post.get("share_to_feed", True), bool):
        problems.append("share_to_feed must be true or false")
    if list(folder.glob("*.mp4")) or list(folder.glob("*.mov")):
        problems.append(f"the video goes on the '{REELS_RELEASE}' release, not in this folder (see SETUP.md)")
    if post.get("cover"):
        problems += check_jpeg(folder / post["cover"], post["cover"])[0]
    url = reel_release_url(folder.name)
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)
    except urllib.error.HTTPError as e:
        problems.append(f"{folder.name}.mp4 is not on the '{REELS_RELEASE}' release yet (HTTP {e.code}); upload it first")
    except OSError as e:
        problems.append(f"couldn't check the video on GitHub ({e})")
    return problems


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
        else:
            # Catch -04:00 used after the clocks go back (or -05:00 in summer).
            expected = t.replace(tzinfo=None).replace(tzinfo=LOCAL_TZ).utcoffset()
            if t.utcoffset() != expected:
                hours = int(expected.total_seconds() // 3600)
                problems.append(f"publish_at offset is wrong for that date in Connecticut; use {hours:+03d}:00")
    except (TypeError, ValueError):
        problems.append("publish_at is missing or not a date like 2026-10-27T09:00:00-04:00")

    caption = post.get("caption", "")
    if not isinstance(caption, str) or not caption.strip():
        problems.append("caption is empty")
    elif len(caption) > MAX_CAPTION:
        problems.append(f"caption is {len(caption)} characters (max {MAX_CAPTION})")
    elif len(re.findall(r"#\w+", caption)) > MAX_HASHTAGS:
        problems.append(f"more than {MAX_HASHTAGS} hashtags")
    elif len(re.findall(r"@[\w.]+", caption)) > MAX_MENTIONS:
        problems.append(f"more than {MAX_MENTIONS} @mentions")

    if not isinstance(post.get("is_ai_generated", False), bool):
        problems.append("is_ai_generated must be true or false")
    if post.get("reel"):
        return problems + check_reel(folder, post)

    images = post.get("images", [])

    # Optional fields.
    alt = post.get("alt_text")
    if alt is not None:
        if not isinstance(alt, str):
            problems.append("alt_text must be text")
        elif len(alt) > MAX_ALT_TEXT:
            problems.append(f"alt_text is {len(alt)} characters (max {MAX_ALT_TEXT})")
        elif len(images) > 1:
            problems.append("alt_text only works on single-image posts, not carousels")
    if not images:
        problems.append("no images listed")
    if len(images) > MAX_CAROUSEL:
        problems.append(f"{len(images)} images (carousel max {MAX_CAROUSEL})")
    ratios = set()
    for name in images:
        found, size = check_jpeg(folder / name, name)
        problems += found
        if size is None:
            continue
        w, h = size
        r = w / h
        if r < MIN_RATIO - 0.01 or r > MAX_RATIO + 0.01:
            problems.append(f"{name} is {w}x{h}; ratio must be between 4:5 and 1.91:1")
        ratios.add(round(r, 3))
    if len(ratios) > 1:
        problems.append("carousel images have different shapes; Instagram crops them all to the first one")
    return problems


def story_images() -> list[Path]:
    if not STORIES_DIR.exists():
        return []
    return sorted(p for p in STORIES_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))


def load_story_config() -> dict:
    path = STORIES_DIR / "config.json"
    return json.loads(path.read_text()) if path.exists() else {}


def check_stories() -> list[str]:
    """Problems with the stories/ rotation: its config and every image in the pool."""
    if not STORIES_DIR.exists():
        return []
    problems = []
    try:
        cfg = load_story_config()
    except ValueError as e:
        return [f"stories/config.json is not valid JSON ({e})"]
    for t in cfg.get("times", []):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(t)):
            problems.append(f'stories/config.json: time "{t}" should look like "09:00" or "18:30"')
    days = cfg.get("min_days_between_repeats", 7)
    if not isinstance(days, (int, float)) or days < 0:
        problems.append("stories/config.json: min_days_between_repeats must be a number of days")
    for p in story_images():
        found, size = check_jpeg(p, f"stories/{p.name}")
        problems += found
        if size and abs(size[0] / size[1] - STORY_RATIO) > 0.02:
            problems.append(f"stories/{p.name} is {size[0]}x{size[1]}; stories should be 9:16, e.g. 1080x1920")
    others = [p.name for p in STORIES_DIR.iterdir()
              if p.is_file() and p.suffix.lower() not in (".jpg", ".jpeg", ".json", ".md") and p.name != "PAUSED"]
    if others:
        problems.append("stories/ only takes JPEGs; not used: " + ", ".join(sorted(others)))
    return problems


def main() -> int:
    bad = 0
    for problem in check_stories():
        print(f"[FIX] {problem}")
        bad += 1
    if STORIES_DIR.exists():
        print(f"[stories] {len(story_images())} image(s) in the rotation"
              + (" -- PAUSED (see stories/PAUSED)" if (STORIES_DIR / "PAUSED").exists() else ""))
    if not QUEUE_DIR.exists():
        print("queue/ is empty")
        return 1 if bad else 0
    for folder in sorted(p for p in QUEUE_DIR.iterdir() if p.is_dir()):
        result = folder / "result.json"
        done = result.exists()
        if not done and is_draft(folder):
            print(f"[draft] {folder.name}: write the caption in post.json; it won't post until you do")
            continue
        problems = [] if done else check_post(folder)  # done posts: date and rules no longer matter
        if done:
            try:
                tag = json.loads(result.read_text()).get("status", "done")
            except ValueError:
                tag = "done"
        else:
            tag = "ok" if not problems else "FIX"
        print(f"[{tag}] {folder.name}" + ("" if not problems else ": " + "; ".join(problems)))
        if problems and not done:
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
