#!/usr/bin/env python3
"""Checks FB_PAGE_TOKEN: what kind of token it is, which Page it's for, its scopes
and expiry, and whether it matches FB_PAGE_ID. Never prints the token.

  FB_PAGE_ID=... FB_PAGE_TOKEN=... python poster/fb_whoami.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HOST = "https://graph.facebook.com/" + (os.environ.get("FB_GRAPH_VERSION") or "v26.0")
PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()


def get(path: str, params: dict) -> dict:
    url = f"{HOST}/{path}?" + urllib.parse.urlencode({**params, "access_token": TOKEN})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": json.load(e).get("error", {})}


if not (PAGE_ID and TOKEN):
    sys.exit("Set FB_PAGE_ID and FB_PAGE_TOKEN first (SETUP.md, \"Facebook Page\").")

d = get("debug_token", {"input_token": TOKEN})
if "error" in d:
    sys.exit(f"Token check failed: {d['error'].get('message')}")
d = d.get("data", {})
exp = d.get("expires_at")
print(f"Valid:        {d.get('is_valid')}")
print(f"Type:         {d.get('type')}   (needs to be PAGE)")
print(f"App:          {d.get('application')} ({d.get('app_id')})")
print(f"Token's Page: {d.get('profile_id')}   FB_PAGE_ID secret: {PAGE_ID}"
      + ("   MATCH" if str(d.get('profile_id')) == PAGE_ID else "   DIFFERENT"))
print(f"Expires:      {'never' if not exp else datetime.fromtimestamp(exp, timezone.utc).isoformat()}")
print(f"Scopes:       {', '.join(d.get('scopes', []))}")
for g in d.get("granular_scopes", []):
    print(f"  {g.get('scope')}: {', '.join(map(str, g.get('target_ids', []))) or 'all'}")
for need in ("pages_show_list", "pages_read_engagement", "pages_manage_posts"):
    if need not in d.get("scopes", []):
        print(f"MISSING scope: {need}")

me = get("me", {"fields": "id,name"})
print(f"/me:          {me.get('name')} ({me.get('id')})" if "error" not in me
      else f"/me failed:   {me['error'].get('message')}")
