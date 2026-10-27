#!/usr/bin/env python3
"""Checks that IG_ACCESS_TOKEN works and shows which account it posts to.
Also prints how many API posts are left in the current 24-hour window.

  IG_ACCESS_TOKEN=... python poster/whoami.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish  # noqa: E402

if not publish.IG_ACCESS_TOKEN:
    sys.exit("Set IG_ACCESS_TOKEN first (SETUP.md step 4).")
try:
    me = publish.api("GET", "me", {"fields": "user_id,username,account_type"})
except publish.ApiError as e:
    sys.exit(f"Token check failed: {e}")
print(f"Token works. Account: @{me.get('username')}  type: {me.get('account_type')}")
print(f"IG_USER_ID = {me.get('user_id')}")
try:
    lim = publish.api("GET", f"{me['user_id']}/content_publishing_limit", {"fields": "quota_usage,config"})
    d = (lim.get("data") or [{}])[0]
    print(f"API posts used in the last 24h: {d.get('quota_usage')} of {d.get('config', {}).get('quota_total')}")
except publish.ApiError as e:
    print(f"(Could not read the posting limit: {e})")
