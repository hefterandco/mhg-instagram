#!/usr/bin/env python3
"""Posts Instagram Stories from a rotating pool of images in stories/.

Drop 9:16 JPEGs (1080x1920) into stories/. At each time in stories/config.json
the poster picks the image that has gone longest without being posted (new ones
first) and posts it as a Story. An image isn't repeated until at least
min_days_between_repeats days have passed. Every post is logged in
stories/history.json, so nothing is posted twice for the same time slot.

If Instagram flags the account (spam or restricted), the rotation pauses itself
by writing stories/PAUSED. Delete that file to start it again.

Usage:
  python poster/stories.py            # post a Story if one is due
  python poster/stories.py --dry-run  # show what would be posted, post nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish  # noqa: E402
from publish import ApiError, api, base_url, wait_until_ready  # noqa: E402
from queue_check import LOCAL_TZ, STORIES_DIR, check_stories, load_story_config, story_images  # noqa: E402

HISTORY = STORIES_DIR / "history.json"
PAUSED = STORIES_DIR / "PAUSED"
# A slot more than this late is skipped, so a delayed run doesn't post a 9am Story at 4pm.
MAX_LATE_HOURS = 2
# Account-level problems: keep going and Instagram may treat it as more spam.
PAUSE_SUBCODES = {2207050, 2207051}


def load_history() -> list[dict]:
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def save_history(history: list[dict]) -> None:
    HISTORY.write_text(json.dumps(history, indent=1) + "\n")


def due_slot(times: list[str], history: list[dict], now: dt.datetime) -> tuple[str | None, list[str]]:
    """The slot to post now (if any), plus earlier unlogged slots today that are now too late."""
    done = {h["slot"] for h in history}
    today = now.astimezone(LOCAL_TZ).date()
    due = []
    for t in sorted(times):
        hh, mm = map(int, t.split(":"))
        at = dt.datetime(today.year, today.month, today.day, hh, mm, tzinfo=LOCAL_TZ)
        slot = f"{today.isoformat()} {t}"
        if at <= now and slot not in done:
            due.append((slot, (now - at).total_seconds() / 3600))
    if not due:
        return None, []
    latest, late_h = due[-1]
    skipped = [s for s, _ in due[:-1]]
    if late_h > MAX_LATE_HOURS:
        return None, skipped + [latest]
    return latest, skipped


def pick_image(history: list[dict], min_days: float, now: dt.datetime) -> Path | None:
    """New images first, then whichever has gone longest since it was last used."""
    last_used: dict[str, dt.datetime] = {}
    for h in history:
        if h.get("file") and h["status"] in ("published", "failed"):
            last_used[h["file"]] = max(last_used.get(h["file"], dt.datetime.min.replace(tzinfo=dt.timezone.utc)),
                                       dt.datetime.fromisoformat(h["at"]))
    pool = story_images()
    fresh = [p for p in pool if p.name not in last_used]
    if fresh:
        return fresh[0]
    ready = [p for p in pool if now - last_used[p.name] >= dt.timedelta(days=min_days)]
    return min(ready, key=lambda p: last_used[p.name]) if ready else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not STORIES_DIR.exists():
        return 0
    if PAUSED.exists():
        print(f"[paused] Stories are paused: {PAUSED.read_text().strip()} -- delete stories/PAUSED to restart")
        return 0
    problems = check_stories()
    if problems:
        print("[skip] Fix stories/ first: " + "; ".join(problems))
        return 1
    if not story_images():
        return 0
    cfg = load_story_config()
    times, min_days = cfg.get("times", []), cfg.get("min_days_between_repeats", 7)

    now = dt.datetime.now(dt.timezone.utc)
    history = load_history()
    slot, skipped = due_slot(times, history, now)
    for s in skipped:
        print(f"[missed] story slot {s}: too late, skipping")
        history.append({"slot": s, "status": "missed", "at": now.isoformat()})
    if not slot:
        if skipped and not args.dry_run:
            save_history(history)
        return 0

    image = pick_image(history, min_days, now)
    if image is None:
        print(f"[skip] story slot {slot}: every image was used in the last {min_days} days; add more to stories/")
        if not args.dry_run:
            history.append({"slot": slot, "status": "skipped", "reason": "nothing new enough", "at": now.isoformat()})
            save_history(history)
        return 0
    if args.dry_run:
        print(f"[dry-run] would post story slot {slot}: {image.name}")
        return 0

    if not publish.IG_ACCESS_TOKEN:
        print("IG_ACCESS_TOKEN is not set yet. Nothing posted. See SETUP.md.")
        return 1
    if not publish.IG_USER_ID:
        publish.IG_USER_ID = str(api("GET", "me", {"fields": "user_id"})["user_id"])
    try:
        container = api("POST", f"{publish.IG_USER_ID}/media",
                        {"media_type": "STORIES", "image_url": f"{base_url()}/stories/{image.name}"})["id"]
        wait_until_ready(container)
        media_id = api("POST", f"{publish.IG_USER_ID}/media_publish", {"creation_id": container})["id"]
    except ApiError as e:
        if not e.permanent:
            print(f"[error] story slot {slot}: {e} -- will retry next run")
            return 1
        print(f"[failed] story slot {slot} ({image.name}): {e}")
        history.append({"slot": slot, "status": "failed", "file": image.name, "reason": str(e), "at": now.isoformat()})
        if e.subcode in PAUSE_SUBCODES:
            PAUSED.write_text(f"{now.isoformat()}: {e}\n")
            print("[paused] Stories paused until stories/PAUSED is deleted")
        save_history(history)
        return 1
    history.append({"slot": slot, "status": "published", "file": image.name, "media_id": media_id, "at": now.isoformat()})
    save_history(history)
    print(f"[published] story slot {slot}: {image.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
