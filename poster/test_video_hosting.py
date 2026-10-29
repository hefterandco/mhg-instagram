#!/usr/bin/env python3
"""Tests whether Instagram can download a video from each URL given.

For each URL it creates a REELS container (Instagram downloads and processes the
video) and reports the container's final status. It NEVER publishes: nothing
appears on the account, and unused containers expire on their own after 24 hours.

Runs from .github/workflows/test-video-hosting.yml:
  python poster/test_video_hosting.py "label=https://..." ["label=https://..." ...]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish  # noqa: E402
from publish import ApiError, api  # noqa: E402


def try_url(user_id: str, url: str) -> str:
    try:
        cid = api("POST", f"{user_id}/media", {
            "media_type": "REELS", "video_url": url, "share_to_feed": "false",
        })["id"]
    except ApiError as e:
        return f"REJECTED at upload: {e} (code {e.code}, subcode {e.subcode})"
    for _ in range(publish.STATUS_POLL_TRIES):
        time.sleep(publish.STATUS_POLL_SECONDS)
        try:
            info = api("GET", cid, {"fields": "status_code,status"})
        except ApiError as e:
            return f"FAILED checking status: {e}"
        code = info.get("status_code")
        if code == "FINISHED":
            return "WORKS: Instagram downloaded and processed the video (not published)"
        if code in ("ERROR", "EXPIRED"):
            return f"FAILED: {code}: {info.get('status', '')}"
    return "UNKNOWN: still processing after 5 minutes"


def main() -> int:
    if not publish.IG_ACCESS_TOKEN:
        print("IG_ACCESS_TOKEN is not set. See SETUP.md.")
        return 1
    user_id = publish.IG_USER_ID or str(api("GET", "me", {"fields": "user_id"})["user_id"])
    summary = ["| Host | Result |", "|---|---|"]
    for arg in sys.argv[1:]:
        label, _, url = arg.partition("=")
        result = try_url(user_id, url)
        print(f"::notice title={label}::{result}")
        summary.append(f"| {label} | {result} |")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text("\n".join(summary) + "\n")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
