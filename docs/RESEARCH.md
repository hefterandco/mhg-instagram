# Meta API research: organic publishing for My House Guardian

Researched 2026-10-29 from Meta's official developer docs (developers.facebook.com) and GitHub's docs. Each claim links to the page it came from. **⚠️ UNCONFIRMED** marks anything the docs contradict or don't state.

The repo today uses **Instagram API with Instagram Login** (host `graph.instagram.com`, Instagram User token, no Facebook Page needed). Most of this research is framed around that setup.

---

## 0. Which "Instagram API" this is

Meta offers three ways in, and they don't share tokens or hosts ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing)):

| Login type | Token | Host | Publishing permissions |
|---|---|---|---|
| **Instagram Login** (what we use) | Instagram User token | `graph.instagram.com` | `instagram_business_basic`, `instagram_business_content_publish` |
| Facebook Login for Business | Facebook Page token | `graph.facebook.com`, `rupload.facebook.com` | `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` (+ `ads_management`/`ads_read` if the user has a Business Manager role on the Page) |
| Unified Login | Business Integration System User token | `graph.facebook.com`, `rupload.facebook.com` | `instagram_basic`, `instagram_content_publish` |

**Why this matters:** the Facebook Login path can require **ad permissions** (`ads_management`/`ads_read`) when the user has a Business Manager role on the Page ([IG User Media reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)). Instagram Login never does, so it fits the "organic only, no ads" rule best.

---

## 1. Instagram content publishing

### What the API can publish
Single images, single videos, Reels, Stories and carousels ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing)). All three login types can publish all of these. The flow is always: create a container (`POST /<IG_ID>/media`), wait until `status_code` is `FINISHED`, then call `POST /<IG_ID>/media_publish` with `creation_id`.

- **Images:** `image_url`, plus an optional `caption` and `alt_text`.
- **Carousel:** create each child with `is_carousel_item=true`, then a parent with `media_type=CAROUSEL` and `children=<comma-separated ids>`. A carousel counts as one post.
- **Reels:** `media_type=REELS`, `video_url`, optional `cover_url`, `thumb_offset`, `share_to_feed`, `audio_name`, `trial_params`.
- **Stories:** `media_type=STORIES` with `image_url` or `video_url`.
- **Resumable (large-file) video uploads** via `rupload.facebook.com` are **only for Facebook Login for Business** apps. With Instagram Login, video has to be a public `video_url`.
- **Not supported:** shopping tags, filters ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing)), and Story stickers (link, poll, location) ([IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)).

### Media specs ([IG User Media reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media))

| | Feed image | Reel | Story |
|---|---|---|---|
| Format | **JPEG only** (no MPO/JPS) | MOV or MP4, moov atom at the front, no edit lists | JPEG image, or video like Reels |
| Max size | 8 MB | 300 MB | 8 MB image / 100 MB video |
| Aspect ratio | **4:5 to 1.91:1** | 0.01:1 to 10:1, 9:16 recommended | 9:16 recommended |
| Dimensions | width 320–1440 px (scaled outside that) | max 1920 px wide | — |
| Duration | — | 3 s – 15 min | 3 s – 60 s |
| Video | — | H.264 or HEVC, 23–60 fps, ≤25 Mbps VBR, closed GOP, 4:2:0; AAC ≤48 kHz, 128 kbps | same as Reels |
| Color | sRGB (others converted) | — | sRGB |

- **Captions:** max 2,200 characters, 30 hashtags, 20 @mentions. Carousel children can't have captions.
- **`alt_text`:** image posts only, up to 1,000 characters; not Reels or Stories (added Mar 24, 2025, per the [changelog](https://developers.facebook.com/documentation/instagram-platform/changelog.md)).
- **`collaborators`:** up to 3 usernames, on feed images, Reels and carousels.
- **`is_ai_generated`:** applies the "AI info" label (added Jun 22, 2026). On carousels, set it on the parent only ([changelog](https://developers.facebook.com/documentation/instagram-platform/changelog.md)).
- **Carousel cropping:** every image is cropped to the first image's aspect ratio, and the default is 1:1 ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing)).
- Reels can't go inside a carousel ([IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)).

### Carousel size: ⚠️ UNCONFIRMED (the docs conflict)
- [Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing) and [IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media) say **up to 20** items.
- The [Error Codes](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/error-codes.md) table still has code 100 / subcode 2207028: "carousel has fewer than 2 or more than **10**".
- **Takeaway:** treat 10 as the safe maximum until a real 11+ item carousel posts successfully.

### Rate limits: ⚠️ the docs conflict
- **Publishing:** the rate-limit section of [Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing) says **100** API-published posts per rolling 24 hours, while its carousel section says **50**. The [content_publishing_limit reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit.md) shows `quota_total: 50`, `quota_duration: 86400`.
  - **Takeaway:** trust whatever `GET /<IG_ID>/content_publishing_limit` returns (`whoami.py` already reads it). Either number is far above our pace.
- **Container creation:** 400 containers per rolling 24 hours ([IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)).
- **Carousels count as one post** ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing)). The content_publishing_limit page doesn't say.

### Container lifecycle ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing))
- **Status codes:** `IN_PROGRESS`, `FINISHED`, `PUBLISHED`, `ERROR`, and `EXPIRED` (not published within 24 hours).
- **Polling:** Meta recommends checking **once per minute, for no more than 5 minutes**.

---

## 2. Cross-posting to the My House Guardian Facebook Page

**The current Instagram Login token cannot post to a Facebook Page.** Pages use the Pages API on `graph.facebook.com` with a **Page access token** obtained through **Facebook Login** ([Pages API: Posts](https://developers.facebook.com/docs/pages-api/posts)). It's a separate login, token and permission set.

### What it needs
- **Permissions:**
  - Posting: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` ([Page Photos reference](https://developers.facebook.com/docs/graph-api/reference/page/photos)).
  - The Posts guide also lists `pages_manage_engagement`, `pages_read_user_engagement`, and `publish_video` for video ([Pages API: Posts](https://developers.facebook.com/docs/pages-api/posts)).
  - The Getting Started page lists `pages_manage_metadata` and `pages_show_list` as well ([Pages API: Getting Started](https://developers.facebook.com/docs/pages-api/getting-started)). Needing it for posting is ⚠️ UNCONFIRMED.
  - None of these are ad permissions.
- **Page role:** the person who logs in must be able to do the `CREATE_CONTENT` task on the Page ([Page Photos](https://developers.facebook.com/docs/graph-api/reference/page/photos)).
- **Getting the token:** `GET /{user-id}/accounts` with a **long-lived** user token returns a Page token. Meta says "Long-lived Page access token do not have an expiration date" ([Long-Lived Tokens](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived)).
  - That means no weekly refresh is needed for Facebook. They can still be invalidated "under certain conditions", which that page doesn't list. Password change, losing the Page role or removed permissions are the usual causes. ⚠️ UNCONFIRMED on that page.

### Endpoints
- **Single photo:** `POST /{page-id}/photos` with `url=<public image URL>` and the caption as `message`. It returns `id` and `post_id` ([Pages API: Posts](https://developers.facebook.com/docs/pages-api/posts)).
- **Multi-photo:** upload each photo with `published=false`, then `POST /{page-id}/feed` with `attached_media[n]={"media_fbid":"<id>"}` ([Page Photos](https://developers.facebook.com/docs/graph-api/reference/page/photos)).
  - Unpublished uploads are deleted after about 24 hours.
  - Facebook accepts JPEG, BMP, PNG, GIF and TIFF up to 10 MB, so our JPEGs work as-is.
- **Native scheduling:** `published=false` plus `scheduled_publish_time`, between 10 minutes and 30 days ahead ([Pages API: Posts](https://developers.facebook.com/docs/pages-api/posts)). We don't need this, because our own scheduler already handles timing.
- **Video and Reels to Pages:** handled by a separate Video API that I didn't research.
- An app can only update a Page post that the same app made.

### Zero-code alternative ⚠️ UNCONFIRMED
Instagram's in-app setting to automatically share posts to a linked Facebook Page (Accounts Center) isn't in the developer docs, so I couldn't confirm it applies to API-published posts. It's worth a manual test: turn it on, let one queued post publish, and check the Page.

---

## 3. Tokens, permissions and App Review

### Instagram Login token (what we use)
- **Refresh:** `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<token>` ([Business Login for Instagram](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)).
  - The token must be **at least 24 hours old** and **not expired**, and the user must have granted `instagram_business_basic`.
  - Each refresh returns a new token good for another **60 days**.
  - A token that goes 60 days without a refresh **expires permanently**, and you have to log in again.
- **Scope names:** `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_comments`, `instagram_business_manage_messages`. The old `business_*` names were deprecated Jan 27, 2025 (same page).
- **Insights scope:** reading insights needs `instagram_business_manage_insights` too ([Insights](https://developers.facebook.com/documentation/instagram-platform/insights.md)). The repo's current token was generated with only basic and content_publish, so **a new token with the insights scope is needed** before it can read insights.

### App Review
- **Not required.** Meta's App Review table lists "My app is only for a business I own or manage" with Instagram Login and Standard Access as App Review "Not required" ([Instagram App Review](https://developers.facebook.com/documentation/instagram-platform/app-review.md)).
- **Standard Access** is enough when the app serves only accounts you own or manage that are added in the App Dashboard. Advanced Access is for other people's accounts ([Business Login for Instagram](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)).
- **General Graph API rule:** Business apps are automatically approved for Standard Access to all permissions, but it only works for people with a role on the app. Advanced Access needs App Review and Business Verification ([Access Levels](https://developers.facebook.com/docs/graph-api/overview/access-levels)).
  - For a Facebook Page cross-post, that means the person who logs in must have a role on the app, and then no App Review is needed.
- **Development vs. Live mode** for Business and Instagram Login apps isn't spelled out in the pages I read. ⚠️ UNCONFIRMED. The repo already works in Development mode, which suggests it's fine.

### API versions
- **Unversioned calls** use whatever version is set in the app dashboard (Settings › Advanced › Upgrade API Version). Meta recommends always specifying a version. Each version works for at least 2 years ([Versioning](https://developers.facebook.com/docs/graph-api/guides/versioning)).
- **Current versions:** v26.0 (Jul 29, 2026, latest), v25.0 (until Jul 29, 2028), v24.0 (until Feb 18, 2028), v23.0 (until Oct 8, 2027) ([Graph API changelog](https://developers.facebook.com/docs/graph-api/changelog)).
- The Instagram insights reference also calls v26.0 the latest ([IG Media Insights](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media/insights.md)).

---

## 4. Reading post insights back

### Instagram ([IG Media Insights](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media/insights.md))
- **Call:** `GET https://graph.instagram.com/v26.0/<IG_MEDIA_ID>/insights?metric=<list>`. It needs `instagram_business_basic` and `instagram_business_manage_insights`.
- **Metrics:**

| Metric | Feed post | Reel | Story |
|---|---|---|---|
| `reach`, `views`, `shares`, `total_interactions`, `reposts` | ✓ | ✓ | ✓ |
| `saved`, `likes`, `comments` | ✓ | ✓ | |
| `follows`, `profile_visits`, `profile_activity` | ✓ | | ✓ |
| `ig_reels_avg_watch_time`, `reels_skip_rate` | | ✓ | |

- **Dead metrics:** `impressions` and `plays` were deprecated for every API version as of Apr 21, 2025 ([changelog](https://developers.facebook.com/documentation/instagram-platform/changelog.md)), and `impressions` errors on media created after Jul 2, 2024. `video_views` is gone too. **Use `views`.**
- **Quick counts:** media objects have `saved_count`, `shares_count` and `reposts_count` fields (added Apr 22, 2026, [changelog](https://developers.facebook.com/documentation/instagram-platform/changelog.md)).
- **Limits:**
  - Data can lag **up to 48 hours**.
  - It's kept for up to 2 years.
  - Unavailable data comes back as an **empty set, not 0**.
  - Children inside a carousel have **no** insights; read them on the carousel itself.
  - Story metrics vanish after 24 hours.
  - The `total_*` metrics, which include paid activity, are Facebook Login only. They aren't relevant to us anyway.
  - Some metrics are unavailable on accounts with **fewer than 100 followers** ([Insights overview](https://developers.facebook.com/documentation/instagram-platform/insights.md)).
  - Insights webhooks aren't supported with Instagram Login, so we'd have to poll.

### Facebook Page ([Graph API Insights](https://developers.facebook.com/docs/graph-api/reference/insights))
- **Needs:** `read_insights` and `pages_read_engagement`, plus the `ANALYZE` task on the Page.
- **"Page Insights data is only available on Pages with 100 or more likes."**
- **Deprecations:** `post_impressions*` is deprecated above v25, and "By June 15, 2026, a number of the Page Insights metrics will be deprecated for all API versions." Use `post_media_view` and `post_total_media_view_unique`.

---

## 5. Failure modes and how to handle them

From [Instagram Error Codes](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/error-codes.md) unless noted.

| Code / subcode | Meaning | What to do |
|---|---|---|
| -1 / 2207001, 2207032 | Instagram server error / container creation failed | **Retry** |
| -1 / 2207053 | Unknown upload error (mostly video) | Retry with a **new container** |
| -2 / 2207003 | Media download timed out | **Retry** |
| -2 / 2207020 | Container expired (older than 24 hours) | New container |
| 9007 / 2207027 | Not ready to publish | Poll `status_code` until `FINISHED`, then publish |
| 24 / 2207008 | Container missing or expired at publish time | Retry 1–2 times over 30 s – 2 min, then a new container |
| 24 / 2207006 | Media not found (permissions or expired token) | Check the token, then a new container |
| 9004 / 2207052 | **Media URL couldn't be fetched** | Fix hosting (the URL must be public); don't blind-retry |
| 36000 / 2207004 | Image over 8 MiB | Fix the file |
| 36001 / 2207005 | Unsupported image format | Use JPEG |
| 36003 / 2207009 | Aspect ratio outside 4:5–1.91:1 | Fix the file |
| 36004 / 2207010 | Caption too long, or too many hashtags or mentions | Fix the caption |
| 9 / 2207042 | Daily publishing limit reached | Wait until the next day |
| 4 / 2207051 | **Flagged as spam** | Stop; the account owner contests it in the app. **Don't retry.** |
| 25 / 2207050 | Account inactive, checkpointed or restricted | Stop; fix it in the Instagram app |
| 190 | Expired or invalid token | Not in the Instagram error table ⚠️. In the general Graph API it means an invalid OAuth token. Re-authenticate. |

### Other failure modes
- **Media hosting:** media must be on a **public server at the moment of publishing**, because Meta fetches it with cURL ([Publish Content](https://developers.facebook.com/docs/instagram-platform/content-publishing)).
  - This repo serves images from `raw.githubusercontent.com/<repo>/<commit-sha>/…`. That works **only because the repo is public**; I checked and it returns `200 image/jpeg`. Making the repo private would break publishing (code 9004).
  - Whether `raw.githubusercontent.com` serves MP4 with a content type Meta accepts for Reels is ⚠️ UNCONFIRMED.
- **Token expiry:** a token that isn't refreshed within 60 days dies permanently ([Business Login for Instagram](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)). The weekly refresh also depends on `GH_SECRETS_TOKEN`, which expires after 1 year, so that's a second expiry date to track.
- **GitHub schedule** ([GitHub: events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)):
  - Scheduled runs "can be delayed during periods of high loads", and the start of each hour is busiest.
  - "some queued jobs may be dropped".
  - The minimum interval is 5 minutes.
  - Schedules run on the default branch only.
  - In public repos, schedules are **disabled after 60 days with no repository activity**.
