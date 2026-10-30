"""Cross-posts a published Instagram post to the My House Guardian Facebook Page.

Facebook Pages API (graph.facebook.com) with a Page access token. Photos go to
/{page-id}/photos, several photos become one /feed post with attached_media, and
reels go through the three-step Reels upload (start, upload, finish).
Docs: docs/RESEARCH.md section 2.

Off unless both FB_PAGE_ID and FB_PAGE_TOKEN are set, so nothing changes until
the Page is connected (SETUP.md, "Facebook Page").
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")        # SECRET  the Page's numeric ID
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")  # SECRET  Page token, or a User token that manages the Page
FB_HOST = "https://graph.facebook.com"
FB_UPLOAD_HOST = "https://rupload.facebook.com"
FB_VERSION = os.environ.get("FB_GRAPH_VERSION") or "v26.0"

STATUS_POLL_SECONDS = 30
STATUS_POLL_TRIES = 8  # up to 4 minutes per run; a slow reel carries over to the next run

# Errors that will fail the same way every time: bad token (190), missing
# permission (10, 200-299), bad parameter (100). Everything else is retried.
PERMANENT_CODES = {10, 100, 190}


def enabled() -> bool:
    return bool(FB_PAGE_ID and FB_PAGE_TOKEN)


class FacebookError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code

    @property
    def permanent(self) -> bool:
        return self.code in PERMANENT_CODES or (self.code is not None and 200 <= self.code <= 299)


class NotReadyYet(FacebookError):
    """Facebook is still processing the reel; finish it next run."""


def _send(req: urllib.request.Request, label: str) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err = json.loads(body).get("error", {})
        except ValueError:
            err = {"message": body[:300]}
        code = err.get("code")
        hint = " (the Page token is invalid: make a new one, see SETUP.md)" if code == 190 else ""
        raise FacebookError(f"{label}: {err.get('message', body[:300])}{hint}", code) from None


_page_token: str | None = None


def page_token() -> str:
    """The Page access token. If FB_PAGE_TOKEN is a User token (the long-lived one
    from the Access Token Tool), swap it for the Page's own token, which Reels need."""
    global _page_token
    if _page_token is None:
        url = f"{FB_HOST}/{FB_VERSION}/{FB_PAGE_ID}?" + urllib.parse.urlencode(
            {"fields": "access_token", "access_token": FB_PAGE_TOKEN})
        try:
            _page_token = _send(urllib.request.Request(url), "Facebook page token").get("access_token") or FB_PAGE_TOKEN
        except FacebookError:
            _page_token = FB_PAGE_TOKEN  # already a Page token, or no access; the real call reports it
    return _page_token


def api(method: str, path: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["access_token"] = page_token()
    url = f"{FB_HOST}/{FB_VERSION}/{path.lstrip('/')}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    return _send(urllib.request.Request(url, data=data, method=method), f"Facebook {method} {path}")


def permalink(object_id: str) -> str:
    try:
        link = api("GET", object_id, {"fields": "permalink_url"}).get("permalink_url", "")
    except FacebookError:
        return ""
    return f"https://www.facebook.com{link}" if link.startswith("/") else link


def post_photos(image_urls: list[str], caption: str) -> dict:
    if len(image_urls) == 1:
        res = api("POST", f"{FB_PAGE_ID}/photos", {"url": image_urls[0], "message": caption})
        post_id = res.get("post_id") or res["id"]
    else:
        # Upload each photo unpublished, then publish them together as one post.
        params = {"message": caption}
        for i, u in enumerate(image_urls):
            fbid = api("POST", f"{FB_PAGE_ID}/photos", {"url": u, "published": "false"})["id"]
            params[f"attached_media[{i}]"] = json.dumps({"media_fbid": fbid})
        post_id = api("POST", f"{FB_PAGE_ID}/feed", params)["id"]
    return {"status": "published", "post_id": post_id, "permalink": permalink(post_id)}


def start_reel(video_bytes: bytes) -> str:
    """Steps 1 and 2: open an upload session and send the video. Returns the video ID."""
    video_id = api("POST", f"{FB_PAGE_ID}/video_reels", {"upload_phase": "start"})["video_id"]
    req = urllib.request.Request(
        f"{FB_UPLOAD_HOST}/video-upload/{FB_VERSION}/{video_id}", data=video_bytes, method="POST",
        headers={"Authorization": f"OAuth {page_token()}", "offset": "0",
                 "file_size": str(len(video_bytes)), "Content-Type": "application/octet-stream"})
    _send(req, "Facebook reel upload")
    return video_id


def finish_reel(video_id: str, caption: str) -> dict:
    """Steps 3 and 4: wait for processing, then publish. Raises NotReadyYet if still processing."""
    for i in range(STATUS_POLL_TRIES):
        status = api("GET", video_id, {"fields": "status"}).get("status", {})
        state = status.get("video_status")
        if state in ("upload_failed", "error", "expired"):
            reason = (status.get("processing_phase") or {}).get("error", {}).get("message", "")
            raise FacebookError(f"Facebook reel {video_id} ended with status {state}. {reason}".strip(), 100)
        # The status reads "upload_complete" while the reel waits for the finish call.
        if state in ("ready", "upload_complete"):
            break
        if i < STATUS_POLL_TRIES - 1:
            time.sleep(STATUS_POLL_SECONDS)
    else:
        raise NotReadyYet(f"Facebook reel {video_id} is still processing")
    api("POST", f"{FB_PAGE_ID}/video_reels", {
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED", "description": caption})
    return {"status": "published", "video_id": video_id, "permalink": permalink(video_id)}
