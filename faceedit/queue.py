"""Hands a finished Reel to the auto-poster: uploads the video to the "reels"
GitHub Release and creates its queue folder with a placeholder caption.

The post stays a draft (it never publishes) until the caption is written in
queue/<folder>/post.json. Uses the GitHub login git already saved on this Mac,
or GITHUB_TOKEN from .env.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import REPO, secret

sys.path.insert(0, str(REPO / "poster"))
from queue_check import (  # noqa: E402
    CAPTION_PLACEHOLDER, LOCAL_TZ, QUEUE_DIR, REELS_RELEASE, check_post, repo_slug,
)

MAX_REEL_BYTES = 300 * 1024 * 1024  # Instagram's Reels limit
API = "https://api.github.com"


def github_token() -> str:
    token = secret("GITHUB_TOKEN")
    if token:
        return token
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    for line in out.stdout.splitlines():
        if line.startswith("password="):
            return line.partition("=")[2]
    raise SystemExit("No GitHub login found. Push once from Terminal so your Mac saves it, "
                     "or put GITHUB_TOKEN in .env (see .env.example).")


def gh(method: str, url: str, token: str, data=None, headers: dict | None = None) -> dict | None:
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:300]
        if e.code == 404:
            return None
        if e.code in (401, 403):
            raise SystemExit(f"GitHub refused the upload ({e.code}). The saved token needs "
                             f"Contents: Read and write on this repo. {msg}") from None
        raise SystemExit(f"GitHub error {e.code}: {msg}") from None


def slugify(text: str) -> str:
    text = re.sub(r"\.edit$", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "reel"


def parse_when(when: str) -> dt.datetime:
    try:
        t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        raise SystemExit(f'--at should look like "2026-11-05 09:00" (Connecticut time), not "{when}"') from None
    return t.replace(tzinfo=LOCAL_TZ)


def queue_reel(video: Path, when: str, slug: str | None = None, cover: Path | None = None,
               replace: bool = False) -> Path:
    if not video.exists():
        raise SystemExit(f"Can't find {video}")
    size = video.stat().st_size
    if size > MAX_REEL_BYTES:
        raise SystemExit(f"{video.name} is {size / 2**20:.0f} MB; Instagram's limit for Reels is 300 MB.")
    at = parse_when(when)
    name = f"{at.date().isoformat()}-{slug or slugify(video.stem)}"
    folder = QUEUE_DIR / name
    if folder.exists() and not replace:
        raise SystemExit(f"queue/{name} already exists. Pick another --slug, or use --replace.")
    if cover and not cover.exists():
        raise SystemExit(f"Can't find cover image {cover}")

    repo, token = repo_slug(), github_token()
    release = gh("GET", f"{API}/repos/{repo}/releases/tags/{REELS_RELEASE}", token)
    if not release:
        raise SystemExit(f"There's no '{REELS_RELEASE}' release yet. Create it first: SETUP.md › Reels.")
    asset_name = f"{name}.mp4"
    for asset in release.get("assets", []):
        if asset["name"] == asset_name:
            if not replace:
                raise SystemExit(f"{asset_name} is already on the release. Use --replace to upload over it.")
            gh("DELETE", f"{API}/repos/{repo}/releases/assets/{asset['id']}", token)

    print(f"Uploading {video.name} ({size / 2**20:.1f} MB) to the '{REELS_RELEASE}' release as {asset_name}...")
    upload_url = release["upload_url"].split("{")[0] + "?" + urllib.parse.urlencode({"name": asset_name})
    with open(video, "rb") as f:
        gh("POST", upload_url, token, data=f,
           headers={"Content-Type": "video/mp4", "Content-Length": str(size)})

    folder.mkdir(parents=True, exist_ok=True)
    post = {"publish_at": at.isoformat(), "caption": CAPTION_PLACEHOLDER, "reel": True, "share_to_feed": True}
    if cover:
        (folder / "cover.jpg").write_bytes(cover.read_bytes())
        post["cover"] = "cover.jpg"
    (folder / "post.json").write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")

    # Everything except the caption should check out now.
    problems = [p for p in check_post(folder) if "caption" not in p]
    print(f"Queued: queue/{name}/post.json  (posts {at.strftime('%a %b %-d, %-I:%M %p')} Connecticut time)")
    for p in problems:
        print(f"  problem: {p}")
    print("Next: write the caption in post.json (replace the placeholder), then commit and push.\n"
          "Until the caption is written it stays a draft and won't post.")
    return folder
