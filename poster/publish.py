#!/usr/bin/env python3
"""My House Guardian Instagram auto-poster.

Looks through queue/ for posts whose publish time has arrived, publishes them
through the Instagram API (Instagram Login, graph.instagram.com), and writes a
result.json next to each post so it is never posted twice.

Standard library only. Configuration comes from environment variables; see
SETUP.md for every value and where it comes from.

Usage:
  python poster/publish.py              # publish anything due
  python poster/publish.py --dry-run    # show what would happen, call nothing
  python poster/publish.py --force 2026-10-27-fairfield-1959
                                        # publish one post now, even if late or early
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from queue_check import QUEUE_DIR, check_post, load_post  # noqa: E402

# ---------------------------------------------------------------------------
# Config. Secrets are never hard-coded: fill them in as GitHub secrets
# (or in a local .env for testing). See SETUP.md.
# ---------------------------------------------------------------------------
IG_USER_ID = os.environ.get("IG_USER_ID", "")            # SECRET  e.g. 17841400000000000
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")  # SECRET  long-lived Instagram user token
GRAPH_HOST = os.environ.get("IG_GRAPH_HOST", "https://graph.instagram.com")
# Pinned so a change in the Meta app dashboard can't change behaviour. Override with IG_GRAPH_VERSION.
GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION") or "v26.0"
# Where Instagram can download the images from. In GitHub Actions this is built
# automatically from the repo and the exact commit, so it never serves a stale file.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")
# A post more than this many hours late is marked "missed" instead of posted,
# so turning the poster back on after a break never dumps a week of posts at once.
MAX_LATE_HOURS = float(os.environ.get("MAX_LATE_HOURS", "6"))

STATUS_POLL_SECONDS = 60
STATUS_POLL_TRIES = 6  # once a minute for up to 5 minutes, per Meta's guidance

# Error subcodes that will fail the same way every time, so the post is marked
# "failed" instead of being retried every 15 minutes. From Meta's error code table
# (docs/RESEARCH.md section 5). Everything else is treated as temporary and retried.
PERMANENT_SUBCODES = {
    2207004: "image is over 8 MB",
    2207005: "image format not supported (use JPEG)",
    2207009: "image shape is outside 4:5 to 1.91:1",
    2207010: "caption too long, or too many hashtags or @mentions",
    2207023: "unknown media type",
    2207026: "video format not supported",
    2207028: "carousel needs 2 to 10 items",
    2207040: "too many @ tags (max 20)",
    2207042: "Instagram's daily posting limit was reached",
    2207050: "the Instagram account is inactive, checkpointed or restricted; fix it in the Instagram app",
    2207051: "Instagram flagged this as spam; contest it in the Instagram app before posting again",
    2207052: "Instagram could not download the image; check the repo is public",
}


class ApiError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, subcode: int | None = None):
        super().__init__(message)
        self.code, self.subcode = code, subcode

    @property
    def permanent(self) -> bool:
        return self.subcode in PERMANENT_SUBCODES


def base_url() -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    repo, sha = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_SHA")
    if repo and sha:
        return f"https://raw.githubusercontent.com/{repo}/{sha}"
    raise SystemExit("PUBLIC_BASE_URL is not set and this is not running in GitHub Actions.")


def api(method: str, path: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["access_token"] = IG_ACCESS_TOKEN
    prefix = f"{GRAPH_HOST}/{GRAPH_VERSION}" if GRAPH_VERSION else GRAPH_HOST
    url = f"{prefix}/{path.lstrip('/')}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err = json.loads(body).get("error", {})
        except ValueError:
            err = {"message": body[:300]}
        code, subcode = err.get("code"), err.get("error_subcode")
        hint = ""
        if code == 190:
            hint = " (the access token is expired or invalid: run the Refresh token workflow or paste a new token, see SETUP.md)"
        elif subcode in PERMANENT_SUBCODES:
            hint = f" ({PERMANENT_SUBCODES[subcode]})"
        raise ApiError(f"{method} {path}: {err.get('message', body[:300])}{hint}", code, subcode) from None


def wait_until_ready(container_id: str) -> None:
    for _ in range(STATUS_POLL_TRIES):
        status = api("GET", container_id, {"fields": "status_code"}).get("status_code")
        if status in (None, "FINISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise ApiError(f"container {container_id} ended with status {status}")
        time.sleep(STATUS_POLL_SECONDS)
    raise ApiError(f"container {container_id} was not ready after {STATUS_POLL_TRIES} checks")


def publish(folder: Path, post: dict) -> dict:
    urls = [f"{base_url()}/queue/{folder.name}/{name}" for name in post["images"]]
    caption = post["caption"]
    # Optional post.json fields, passed straight through. Carousel children can't take either.
    extra = {}
    if post.get("is_ai_generated"):
        extra["is_ai_generated"] = "true"
    if len(urls) == 1:
        if post.get("alt_text"):
            extra["alt_text"] = post["alt_text"]
        container = api("POST", f"{IG_USER_ID}/media", {"image_url": urls[0], "caption": caption, **extra})["id"]
    else:
        children = []
        for u in urls:
            cid = api("POST", f"{IG_USER_ID}/media", {"image_url": u, "is_carousel_item": "true"})["id"]
            children.append(cid)
        for cid in children:
            wait_until_ready(cid)
        container = api("POST", f"{IG_USER_ID}/media", {
            "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, **extra,
        })["id"]
    wait_until_ready(container)
    media_id = api("POST", f"{IG_USER_ID}/media_publish", {"creation_id": container})["id"]
    permalink = ""
    try:
        permalink = api("GET", media_id, {"fields": "permalink"}).get("permalink", "")
    except ApiError:
        pass
    return {"media_id": media_id, "permalink": permalink}


def write_result(folder: Path, result: dict) -> None:
    (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", metavar="FOLDER", help="publish this one post now")
    args = ap.parse_args()

    global IG_USER_ID
    if not args.dry_run:
        if not IG_ACCESS_TOKEN:
            print("IG_ACCESS_TOKEN is not set yet. Nothing posted. See SETUP.md.")
            return 1
        if not IG_USER_ID:
            # The token already knows which account it belongs to.
            try:
                IG_USER_ID = str(api("GET", "me", {"fields": "user_id"})["user_id"])
            except ApiError as e:
                print(f"[error] {e}")
                return 1

    now = dt.datetime.now(dt.timezone.utc)
    folders = sorted(p for p in QUEUE_DIR.iterdir() if p.is_dir()) if QUEUE_DIR.exists() else []
    if args.force:
        folders = [QUEUE_DIR / args.force]
        if not folders[0].is_dir():
            print(f"No post folder named {args.force}")
            return 1

    failures = 0
    for folder in folders:
        if (folder / "result.json").exists() and not args.force:
            continue
        problems = check_post(folder)
        if problems:
            print(f"[skip] {folder.name}: " + "; ".join(problems))
            failures += 1
            continue
        post = load_post(folder)
        when = dt.datetime.fromisoformat(post["publish_at"])
        late_h = (now - when).total_seconds() / 3600
        if not args.force:
            if late_h < 0:
                print(f"[wait] {folder.name}: scheduled {when.isoformat()}")
                continue
            if late_h > MAX_LATE_HOURS:
                print(f"[missed] {folder.name}: {late_h:.1f}h late, not posting (use --force to post anyway)")
                if not args.dry_run:
                    write_result(folder, {"status": "missed", "checked_at": now.isoformat()})
                continue
        if args.dry_run:
            print(f"[dry-run] would publish {folder.name}: {len(post['images'])} image(s)")
            continue
        try:
            res = publish(folder, post)
        except ApiError as e:
            failures += 1
            if e.permanent:
                # Retrying won't help (and for spam or restricted accounts, could hurt).
                # Delete result.json after fixing the problem to try again.
                print(f"[failed] {folder.name}: {e} -- not retrying; delete result.json to try again")
                write_result(folder, {"status": "failed", "checked_at": now.isoformat(),
                                      "error_code": e.code, "error_subcode": e.subcode, "reason": str(e)})
            else:
                print(f"[error] {folder.name}: {e} -- will retry next run")
            continue
        write_result(folder, {"status": "published", "published_at": now.isoformat(), **res})
        print(f"[published] {folder.name} {res.get('permalink', '')}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
