"""Reads Facebook Page results into insights/facebook.json. Called by insights.py.

What it records (read-only; never posts, edits or deletes):
  followers   Page follower count per day (Connecticut date)
  posts       every queue post that went to the Page: reactions, comments, shares,
              plus reach/views when the token is allowed to read insights

Reactions, comments, shares and followers need only pages_read_engagement, which
the Page token already has. Reach and views come from the Page insights endpoints,
which need read_insights, and Meta only serves them once a Page has 100 likes. Until
then they stay null (shown as a dash), never 0.

Off unless FB_PAGE_ID and FB_PAGE_TOKEN are set in the workflow step (SETUP.md,
"Facebook Page").

API: https://developers.facebook.com/docs/graph-api/reference/page/
     https://developers.facebook.com/docs/graph-api/reference/v26.0/insights
     https://developers.facebook.com/docs/video-api/guides/reels-publishing (reel IDs are video IDs)
"""
from __future__ import annotations

import datetime as dt
import json

import facebook as fb
from queue_check import LOCAL_TZ, QUEUE_DIR

PERMISSION_CODES = {10, 100, 200}  # 100 also covers "metric not available for this object"
FRESH_DAYS = 30

POST_INSIGHTS = ["post_impressions_unique", "post_impressions"]      # reach, views (photo/feed posts)
REEL_INSIGHTS = ["post_impressions_unique", "blue_reels_play_count"]  # reach, plays (reels)


def summary_count(obj: dict, edge: str):
    s = (obj.get(edge) or {}).get("summary") or {}
    return s.get("total_count")


def read_insights(object_id: str, metrics: list[str]) -> dict:
    """{metric: value or None}. Asks one metric at a time so one refusal doesn't blank the rest."""
    out = {}
    for m in metrics:
        try:
            path = f"{object_id}/video_insights" if m == "blue_reels_play_count" else f"{object_id}/insights"
            rows = fb.api("GET", path, {"metric": m}).get("data", [])
            vals = rows[0].get("values", []) if rows else []
            out[m] = vals[-1].get("value") if vals else None
        except fb.FacebookError as e:
            if e.code not in PERMISSION_CODES and not (e.code and 200 <= e.code <= 299):
                raise
            out[m] = None
    return out


def queue_posts() -> dict[str, dict]:
    """Facebook object ID -> what the queue knows about it, from each result.json."""
    found = {}
    for res_file in sorted(QUEUE_DIR.glob("*/result.json")):
        res = json.loads(res_file.read_text())
        f = res.get("facebook") or {}
        if f.get("status") != "published":
            continue
        post = json.loads((res_file.parent / "post.json").read_text())
        oid = f.get("video_id") or f.get("post_id")
        if oid:
            found[oid] = {"folder": res_file.parent.name, "kind": "reel" if f.get("video_id") else
                          ("carousel" if len(post.get("images", [])) > 1 else "image"),
                          "permalink": f.get("permalink", ""), "posted_at": f.get("published_at")}
    return found


def collect(now: dt.datetime, data: dict) -> dict:
    data.setdefault("followers", {})
    data.setdefault("posts", {})
    page = fb.api("GET", fb.FB_PAGE_ID, {"fields": "followers_count,fan_count"})
    today = now.astimezone(LOCAL_TZ).date().isoformat()
    data["followers"][today] = page.get("followers_count", page.get("fan_count"))

    for oid, info in queue_posts().items():
        rec = data["posts"].get(oid, {})
        rec.update(info)
        posted = dt.datetime.fromisoformat(info["posted_at"]) if info.get("posted_at") else now
        last = rec.get("checked_at")
        if last and (now - posted).days > FRESH_DAYS and (now - dt.datetime.fromisoformat(last)).days < 7:
            data["posts"][oid] = rec
            continue
        # Each field on its own: on photo posts, comments need pages_read_user_content,
        # which the token lacks, and one refused field would otherwise blank the rest.
        wanted = ["likes.summary(true).limit(0)", "comments.summary(true).limit(0)"] if info["kind"] == "reel" else \
            ["reactions.summary(true).limit(0)", "shares", "comments.summary(true).limit(0)"]
        obj, errors = {}, []
        for field in wanted:
            try:
                obj.update(fb.api("GET", oid, {"fields": field}))
            except fb.FacebookError as e:
                errors.append(f"{field.split('.')[0]}: {str(e)[:120]}")
        if errors:
            rec["error"] = "; ".join(errors)
        else:
            rec.pop("error", None)
        rec["reactions"] = summary_count(obj, "likes" if info["kind"] == "reel" else "reactions")
        rec["comments"] = summary_count(obj, "comments")
        rec["shares"] = (obj.get("shares") or {}).get("count", 0) if info["kind"] != "reel" and "id" in obj else None
        ins = read_insights(oid, REEL_INSIGHTS if info["kind"] == "reel" else POST_INSIGHTS)
        rec["reach"] = ins.get("post_impressions_unique")
        rec["views"] = ins.get("blue_reels_play_count") if info["kind"] == "reel" else ins.get("post_impressions")
        rec["checked_at"] = now.isoformat()
        data["posts"][oid] = rec
    data["updated_at"] = now.isoformat()
    return data
