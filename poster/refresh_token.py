#!/usr/bin/env python3
"""Refreshes the long-lived Instagram token (good for 60 days) and saves the new
one back into the repo's IG_ACCESS_TOKEN secret, so posting never stops.

Runs weekly from .github/workflows/refresh-token.yml. Needs:
  IG_ACCESS_TOKEN   the current token (secret)
  GH_SECRETS_TOKEN  a GitHub token allowed to write this repo's secrets (secret)
  GITHUB_REPOSITORY set automatically by GitHub Actions
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPH_HOST = os.environ.get("IG_GRAPH_HOST", "https://graph.instagram.com")


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    gh_token = os.environ.get("GH_SECRETS_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token:
        print("IG_ACCESS_TOKEN is not set. See SETUP.md.")
        return 1

    url = f"{GRAPH_HOST}/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_refresh_token", "access_token": token})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("Refresh failed:", e.read().decode(errors="replace")[:400])
        print("If the token already expired, make a new one in the Meta app dashboard (SETUP.md step 4).")
        return 1

    new_token = data["access_token"]
    days = int(data.get("expires_in", 0)) // 86400
    print(f"::add-mask::{new_token}")
    print(f"Token refreshed; good for about {days} days.")

    if not (gh_token and repo):
        print("GH_SECRETS_TOKEN not set, so the new token was NOT saved. "
              "The old one still works until it expires. See SETUP.md step 6.")
        return 1
    subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo],
                   input=new_token.encode(), check=True,
                   env={**os.environ, "GH_TOKEN": gh_token})
    print("Saved the new token to the IG_ACCESS_TOKEN secret.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
