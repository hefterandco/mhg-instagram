# Improvement plan

Based on [RESEARCH.md](RESEARCH.md) (2026-10-29) and a full read of the repo. **No code has been changed.** Each item says whether it needs a new API, library or service. Under the project rules those need the owner's OK first.

## Overall
The core is sound and matches Meta's current docs:
- It uses Instagram Login, which needs no ad permissions.
- It uses JPEG only, 4:5 to 1.91:1, captions up to 2,200 characters with 30 hashtags, and the container → status → publish flow.
- The weekly refresh (every 7 days against a 60-day token) fits the 24-hour minimum token age.
- App Review isn't needed for our own account.
- Two posts have already published successfully.

The real problems are reliability edge cases that can **double-post** or **silently stop**, a few outdated numbers in the docs, and missing features (insights, Facebook, alt text).

---

## What's wrong or outdated

| # | Where | Problem |
|---|---|---|
| W1 | `.github/workflows/post.yml:56-63` | **Double-post risk.** The job commits `result.json` and runs `git push` with no `git pull --rebase` first. If you push a new queue folder while a run is posting, the push is rejected and `result.json` is lost. The next run 15 minutes later sees no `result.json` and **publishes the same post again**. |
| W2 | `poster/publish.py:118` | **Double-post risk.** If `media_publish` succeeds on Instagram's side but the HTTP response times out or errors, the post stays unmarked and is published again next run. Nothing checks whether it already went up. |
| W3 | `poster/publish.py:184-187` | **Every error is retried every 15 minutes for up to 6 hours** (about 24 attempts). That's fine for server hiccups. It's bad for permanent errors (bad image, caption) and **risky for "flagged as spam" (2207051) or account restricted (2207050)**, where repeated attempts could make it worse. |
| W4 | `poster/publish.py:40`, `SETUP.md:12` | **API version not pinned.** Unversioned calls use whatever version the Meta app dashboard is set to, which can change under you. Meta recommends always pinning. Current version: v26.0. |
| W5 | `poster/queue_check.py:21`, `SETUP.md:70` | **Carousel max is 20, but Meta's own error table still says 2–10** (subcode 2207028). The docs conflict, so 10 is the safe limit until tested. |
| W6 | `SETUP.md:90` | **"Meta allows up to 100 API posts per 24 hours"**: the API's own limit endpoint says 50, and the docs conflict. It doesn't matter at our pace, but the docs should say "about 50; `whoami` shows the real number". |
| W7 | `README.md:15`, `SETUP.md:83` | **The docs say "hourly at :07"**, but `post.yml` runs every 15 minutes (`4,19,34,49`). |
| W8 | `poster/queue_check.py:60-66` | **Wrong daylight-saving offsets go unchecked.** A post on Nov 3 written with `-04:00` would publish an hour off. Clocks change Nov 1. |
| W9 | `poster/publish.py:48-49` | **Polls every 15 s × 20.** Meta recommends once a minute for ≤5 minutes. It's harmless for images, but worth aligning before adding video. |

## What's missing

| # | Gap |
|---|---|
| M1 | **No insights.** Nothing reads reach, saves or shares back, and the current token lacks the `instagram_business_manage_insights` scope. |
| M2 | **No Facebook Page cross-posting.** The Instagram Login token can't post to a Page; it needs Facebook Login and a Page token (see RESEARCH §2). |
| M3 | **No `alt_text`.** It's supported on image posts (up to 1,000 characters), good for accessibility, and costs nothing. |
| M4 | **No expiry alarm for `GH_SECRETS_TOKEN`** (1-year GitHub token). When it lapses, the weekly refresh fails, and 60 days later Instagram posting dies. |
| M5 | **No Reels or Stories.** Possible with Instagram Login via a public `video_url`, but untested with `raw.githubusercontent.com` hosting. |
| M6 | **No `is_ai_generated` flag** in `post.json`, for any post whose image is AI-made. Meta added the label in Jun 2026. |

---

## Ranked improvements (quick wins first)

### Quick wins: small edits, no new APIs or libraries
1. **Fix the result-saving push (W1).** Add `git pull --rebase` before `git push` in `post.yml`, retrying a couple of times. *About 5 lines. Highest value: it closes the most likely double-post path.*
2. **Pin `IG_GRAPH_VERSION` to `v26.0` by default (W4).** Keep the variable as an override. Verify by running **Check Instagram token** once.
3. **Stop retrying permanent errors (W3).**
   - Parse the error `code` and `error_subcode`.
   - For permanent ones (bad media or caption, 2207050, 2207051, 2207042, 9004), write `result.json` with `"status": "failed"` and the reason, so it isn't retried. You'd delete that file to try again.
   - Keep retrying only the transient codes (-1, -2, 2207008, 9007).
4. **Docs and limits cleanup (W5, W6, W7).** Set the carousel max to 10, describe the posting limit as "about 50", and fix the schedule wording in README and SETUP.
5. **Daylight-saving check (W8).** `queue_check.py` warns when `publish_at`'s offset doesn't match New York time for that date. It uses Python's built-in `zoneinfo`, so no new library.
6. **Optional `alt_text` and `is_ai_generated` in `post.json` (M3, M6).** Both are passed straight through to the container. Dropping a folder in still works exactly the same.
7. **Polling cadence (W9):** check once a minute for up to 5 minutes, per Meta.

### Medium: more code, same API, no new services
8. **Double-post guard (W2).** If `media_publish` errors or times out, check the account's most recent media (`GET /me/media?fields=caption,timestamp`) for a matching caption from the last few minutes before giving up. If it's there, record it as published.
9. **Weekly insights (M1).**
   - A new `poster/insights.py` and a weekly workflow write `insights.json` into each posted folder, plus a summary table (`docs/INSIGHTS.md`, or the run log).
   - Metrics: `reach, views, saved, shares, likes, comments, total_interactions, follows, profile_visits`.
   - Read each post at least 48 hours after publishing, and store blanks as blanks, not zeros.
   - **Needs a one-time token regeneration with `instagram_business_manage_insights` added.** It's the same Instagram API, just a new permission. Some metrics may be missing while the account is under 100 followers.
10. **Expiry reminders (M4).** Add a `GH_SECRETS_TOKEN_EXPIRES` variable and have the weekly refresh fail loudly 30 days before that date. GitHub already emails on failure.

### Bigger: needs your OK (new API under your rules)
11. **Cross-post to the Facebook Page (M2).** ✅ Built Oct 30, 2026 (`poster/facebook.py`), approved by Andrew; turns on when `FB_PAGE_ID` and `FB_PAGE_TOKEN` are set. First try the zero-code route: Instagram's own "share to Facebook" setting, published with one test post. It's unconfirmed for API posts. If that doesn't work:
    - **New API: Facebook Pages API** (`graph.facebook.com`).
    - Add Facebook Login to the same Meta app, then generate a long-lived user token → a Page token, which doesn't expire.
    - Two new secrets: `FB_PAGE_ID` and `FB_PAGE_TOKEN`.
    - Permissions: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`. **No ad permissions.**
    - The poster posts the same images and caption via `/{page-id}/photos`, or `attached_media` for multi-image posts.
    - Opt out per post with `"facebook": false` in `post.json`.
    - Track the Facebook result separately in `result.json`, so an Instagram success plus a Facebook failure never re-posts to Instagram.
    - No App Review needed while only people with a role on the app use it.
12. **Reels and Stories (M5).**
    - Accept `reel.mp4` or `story.jpg` in a queue folder.
    - The open question is whether `raw.githubusercontent.com` hosting works for MP4. It needs one real test.
    - Validating video specs before posting needs a tool like `ffprobe`, which counts as a new tool. **Ask first.**
    - If GitHub hosting fails for video, the only alternatives are outside hosting services, which are **a new service. Ask first.**

### Not recommended
- **Switching to Facebook Login for Instagram publishing.** It's the only route to resumable video uploads, but it can require `ads_management`/`ads_read`, which conflicts with the organic-only rule.
- **Making the repo private.** Image hosting depends on the public raw URLs. Going private would need outside hosting, which is a new service.

---

## Suggested order
Items 1–7 as one change (no new anything) → 8 → 9 (after you regenerate the token) → your call on 11 and 12.
