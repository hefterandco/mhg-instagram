#!/usr/bin/env python3
"""Reads Instagram results back into the repo so we can see what's working.

Writes three files under insights/ (see insights/README.md):
  account.json  follower count per day, plus account reach/views/engagement per day
  posts.json    every feed post and Reel on the account, with its latest numbers
  stories.json  every Story caught while it was live (Meta deletes Story numbers after 24h)

Runs about four times a day: the poster workflow calls it with --if-older-than 5.5
on its 15-minute runs (GitHub's own schedule fires unreliably for this repo), and the
"Collect Instagram insights" workflow can also run it by hand or on its own schedule. Read-only:
it never posts, edits or deletes anything on Instagram.

Needs the token to include instagram_business_manage_insights (SETUP.md,
"Insights"). Without it, it still records followers, likes and comments, and
leaves reach and views blank.

Unavailable numbers are stored as null, never 0. Meta returns nothing for some
metrics on accounts under 100 followers, and numbers can lag up to 48 hours.

  python poster/insights.py            # collect and write insights/
  python poster/insights.py --dry-run  # collect and print, write nothing

API: https://developers.facebook.com/docs/instagram-platform/api-reference/instagram-user/insights
     https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish  # noqa: E402
from publish import ApiError, api  # noqa: E402
from queue_check import LOCAL_TZ, QUEUE_DIR, ROOT, STORIES_DIR  # noqa: E402

OUT_DIR = ROOT / "insights"

# Per-media metrics by kind (docs/RESEARCH.md section 4). impressions, plays and video_views are dead.
FEED_METRICS = ["reach", "views", "saved", "likes", "comments", "shares", "total_interactions",
                "follows", "profile_visits"]
REEL_METRICS = ["reach", "views", "saved", "likes", "comments", "shares", "total_interactions",
                "ig_reels_avg_watch_time"]
STORY_METRICS = ["reach", "views", "shares", "total_interactions", "follows", "profile_visits"]
# Account metrics, metric_type=total_value, period=day.
ACCOUNT_METRICS = ["reach", "views", "accounts_engaged", "total_interactions", "likes", "comments",
                   "saves", "shares", "profile_links_taps"]

# Keep refreshing a post's numbers for this long after it goes up, then weekly.
FRESH_DAYS = 30
# Meta's numbers can lag 48 hours; before then a post's numbers are still settling.
SETTLE_HOURS = 48
# Re-read this many finished days of account numbers each run, to pick up Meta's late data.
ACCOUNT_LOOKBACK_DAYS = 3

# Error codes meaning "this token isn't allowed to read insights".
PERMISSION_CODES = {10, 200}


class NoInsightsPermission(Exception):
    pass


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s: str) -> dt.datetime:
    # Instagram returns 2026-10-27T14:23:30+0000
    return dt.datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")


def load(name: str, default):
    p = OUT_DIR / name
    if p.exists():
        return json.loads(p.read_text())
    return default


def save(name: str, data) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / name).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def read_values(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        if "total_value" in r:
            out[r["name"]] = r["total_value"].get("value")
        else:
            vals = r.get("values") or []
            out[r["name"]] = vals[-1].get("value") if vals else None
    return out


def fetch_metrics(path: str, metrics: list[str], extra: dict | None = None) -> dict:
    """All metrics in one call; if Meta rejects one, ask one at a time so the rest still land.
    Anything Meta won't give us comes back as None."""
    params = dict(extra or {})
    try:
        got = read_values(api("GET", path, {**params, "metric": ",".join(metrics)}).get("data", []))
        return {m: got.get(m) for m in metrics}
    except ApiError as e:
        if e.code == 190:
            raise
        if e.code in PERMISSION_CODES:
            raise NoInsightsPermission(str(e)) from None
    out = {}
    for m in metrics:
        try:
            got = read_values(api("GET", path, {**params, "metric": m}).get("data", []))
            out[m] = got.get(m)
        except ApiError as e:
            if e.code == 190:
                raise
            if e.code in PERMISSION_CODES:
                raise NoInsightsPermission(str(e)) from None
            out[m] = None
    return out


def list_media() -> list[dict]:
    fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
    items, after = [], None
    for _ in range(20):  # 20 pages x 50 = 1,000 posts; plenty
        params = {"fields": fields, "limit": 50}
        if after:
            params["after"] = after
        page = api("GET", "me/media", params)
        items += page.get("data", [])
        after = (page.get("paging") or {}).get("cursors", {}).get("after")
        if not (page.get("paging") or {}).get("next"):
            break
    return items


def queue_folders() -> dict[str, str]:
    """media_id -> queue folder name, so the dashboard can use the names Andrew already knows."""
    out = {}
    for res in QUEUE_DIR.glob("*/result.json"):
        try:
            mid = json.loads(res.read_text()).get("media_id")
        except ValueError:
            continue
        if mid:
            out[str(mid)] = res.parent.name
    return out


def story_files() -> dict[str, str]:
    p = STORIES_DIR / "history.json"
    if not p.exists():
        return {}
    return {str(h["media_id"]): h.get("file") for h in json.loads(p.read_text())
            if h.get("status") == "published" and h.get("media_id")}


def kind_of(m: dict) -> str:
    if m.get("media_product_type") == "REELS" or m.get("media_type") == "VIDEO":
        return "reel"
    if m.get("media_type") == "CAROUSEL_ALBUM":
        return "carousel"
    return "image"


def collect_posts(now: dt.datetime, posts: dict, can_insight: bool) -> tuple[dict, bool]:
    folders = queue_folders()
    for m in list_media():
        mid = str(m["id"])
        posted = parse_ts(m["timestamp"])
        age_h = (now - posted).total_seconds() / 3600
        rec = posts.get(mid, {})
        rec.update({
            "folder": folders.get(mid, rec.get("folder")),
            "kind": kind_of(m),
            "permalink": m.get("permalink"),
            "posted_at": posted.isoformat(),
            "caption_start": (m.get("caption") or "").split("\n")[0][:80],
            "like_count": m.get("like_count"),
            "comments_count": m.get("comments_count"),
            "settling": age_h < SETTLE_HOURS,
        })
        last = rec.get("insights_at")
        stale = not last or (now - dt.datetime.fromisoformat(last)).days >= 7
        if can_insight and (age_h < FRESH_DAYS * 24 or stale):
            metrics = REEL_METRICS if rec["kind"] == "reel" else FEED_METRICS
            try:
                rec["metrics"] = fetch_metrics(f"{mid}/insights", metrics)
                rec["insights_at"] = now.isoformat()
            except NoInsightsPermission:
                can_insight = False
        posts[mid] = rec
    return posts, can_insight


def collect_stories(now: dt.datetime, stories: dict, can_insight: bool) -> tuple[dict, bool]:
    files = story_files()
    live = api("GET", "me/stories", {"fields": "id,media_type,timestamp,permalink"}).get("data", [])
    for s in live:
        sid = str(s["id"])
        rec = stories.get(sid, {})
        rec.update({"posted_at": parse_ts(s["timestamp"]).isoformat(), "file": files.get(sid, rec.get("file"))})
        if can_insight:
            try:
                rec["metrics"] = fetch_metrics(f"{sid}/insights", STORY_METRICS)
                rec["insights_at"] = now.isoformat()
            except NoInsightsPermission:
                can_insight = False
        stories[sid] = rec
    return stories, can_insight


def collect_account(now: dt.datetime, account: dict, can_insight: bool) -> tuple[dict, bool]:
    me = api("GET", "me", {"fields": "user_id,followers_count,follows_count,media_count"})
    today = now.astimezone(LOCAL_TZ).date().isoformat()
    # Last reading of the day wins, so each date holds that evening's count.
    account.setdefault("followers", {})[today] = me.get("followers_count")
    account.setdefault("media_count", {})[today] = me.get("media_count")
    if can_insight:
        days = account.setdefault("days", {})
        local_midnight = now.astimezone(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        for back in range(1, ACCOUNT_LOOKBACK_DAYS + 1):
            start = local_midnight - dt.timedelta(days=back)
            end = start + dt.timedelta(days=1)
            try:
                vals = fetch_metrics(f"{me['user_id']}/insights", ACCOUNT_METRICS, {
                    "metric_type": "total_value", "period": "day",
                    "since": int(start.timestamp()), "until": int(end.timestamp()),
                })
            except NoInsightsPermission:
                can_insight = False
                break
            days[start.date().isoformat()] = vals
    return account, can_insight


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--if-older-than", type=float, metavar="HOURS",
                    help="skip unless the last collection is at least this many hours old")
    args = ap.parse_args()
    if args.if_older_than:
        last = load("account.json", {}).get("updated_at")
        if last:
            age = (now_utc() - dt.datetime.fromisoformat(last)).total_seconds() / 3600
            if age < args.if_older_than:
                print(f"Insights collected {age:.1f}h ago; next collection after {args.if_older_than}h.")
                return 0
    if not publish.IG_ACCESS_TOKEN:
        sys.exit("Set IG_ACCESS_TOKEN first (SETUP.md step 4).")

    now = now_utc()
    can = True
    try:
        account, can = collect_account(now, load("account.json", {}), can)
        posts, can = collect_posts(now, load("posts.json", {}), can)
        stories, can = collect_stories(now, load("stories.json", {}), can)
    except ApiError as e:
        sys.exit(f"Insights run failed: {e}")

    account["updated_at"] = now.isoformat()
    account["insights_permission"] = can
    if args.dry_run:
        print(json.dumps({"account": account, "posts": posts, "stories": stories}, indent=1))
    else:
        save("account.json", account)
        save("posts.json", posts)
        save("stories.json", stories)

    print(f"Followers today: {account['followers'].get(now.astimezone(LOCAL_TZ).date().isoformat())}")
    print(f"Posts tracked: {len(posts)}   Stories tracked: {len(stories)}")
    if not can:
        print("::warning::The Instagram token can't read insights yet, so reach and views are blank. "
              "Regenerate it with instagram_business_manage_insights ticked (SETUP.md, 'Insights').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
