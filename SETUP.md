# Setup: connect the auto-poster to Instagram

One-time, about 30 minutes. Everything here is free.

## Fill-in-the-blank: every key this needs

| Name | Where it goes | Secret? | What it is | Where you get it |
|---|---|---|---|---|
| `IG_ACCESS_TOKEN` | GitHub › Settings › Secrets and variables › Actions › **Secrets** | **Yes** | Long-lived Instagram token, good for 60 days. Refreshed automatically every Monday. | Step 4 |
| `IG_USER_ID` | Same place, **Secrets** | Yes (treat as private) | Your Instagram professional account ID. Optional: the poster looks it up from the token if blank. | Step 5 |
| `GH_SECRETS_TOKEN` | Same place, **Secrets** | **Yes** | GitHub token that lets the weekly refresh save the new Instagram token. | Step 6 |
| `IG_GRAPH_VERSION` | Same page, **Variables** tab | No | Optional. The poster uses API version `v26.0` unless you set this, e.g. to try a newer version. | — |
| `MAX_LATE_HOURS` | Same page, **Variables** tab | No | Optional, default `6`. A post this many hours late is skipped and marked "missed" instead of posted. | — |

Nothing else. No paid services. Meta's app secret is **not** needed for this.

---

## 1. Instagram account (done)
`@` My House Guardian is already a **Business** account. Nothing to do. You do *not* need a Facebook Page for this setup.

## 2. Create a Meta developer account
1. Go to developers.facebook.com and log in with the Facebook account you want to own the app.
2. Click **Get started** and finish registering as a developer (it asks to verify a phone number or card on file).

## 3. Create the app
1. **My Apps › Create app.**
2. App name: `MHG Poster`. Contact email: your MHG email.
3. When it asks what the app is for, pick the Instagram use case ("Manage messaging & content on Instagram"). If it asks for an app type, choose **Business**.
4. Don't connect a business portfolio unless it asks; you can skip it.
5. Leave the app in **Development** mode. Because you're only posting to your own account, you do not need App Review.

## 4. Generate the token
1. In the app's left menu: **Instagram › API setup with Instagram business login**.
2. Under **Generate access tokens**, click **Add account** and log in as the My House Guardian Instagram.
3. Click **Generate token** next to the account, approve the permissions, and copy the token.
   - Make sure the permissions include **instagram_business_basic** and **instagram_business_content_publish**.
   - This token is the long-lived kind, good for 60 days.
4. In GitHub: repo › **Settings › Secrets and variables › Actions › New repository secret**
   Name `IG_ACCESS_TOKEN`, value: the token.

## 5. Check the token (and get your user ID)
1. Repo › **Actions › Check Instagram token › Run workflow**.
2. Open the run. It should say `Token works. Account: @yourhandle  type: BUSINESS` and print `IG_USER_ID = 1784…`.
3. Optional: save that number as the `IG_USER_ID` secret. It saves one API call per run.

## 6. Let the token refresh itself
The token dies after 60 days unless it's refreshed. The **Refresh Instagram token** workflow does it every Monday, but it needs permission to save the new token:
1. GitHub › your profile › **Settings › Developer settings › Personal access tokens › Fine-grained tokens › Generate new token.**
2. Name `mhg-poster secrets`. Expiration: 1 year (put a reminder in your calendar).
3. Repository access: **Only select repositories** › this repo.
4. Permissions › Repository permissions › **Secrets: Read and write**. Nothing else.
5. Copy it and save it as the repo secret `GH_SECRETS_TOKEN`.
6. Run **Actions › Refresh Instagram token › Run workflow** once to confirm it says "Saved the new token".

## 7. Test without posting
**Actions › Post to Instagram › Run workflow**, keep **Dry run** checked. It lists what's waiting and when.

## 8. Go live
Nothing to switch on: the hourly run publishes anything whose `publish_at` time has arrived. To post one right away, run **Post to Instagram** with Dry run unchecked and the folder name in **force**.

---

## How posts are queued

```
queue/
  2026-10-27-fairfield-1959/
    post.json
    1.jpg            ← 1080×1350 JPEG (2.jpg, 3.jpg… makes a carousel, up to 10)
```

`post.json`:
```json
{
  "publish_at": "2026-10-27T11:00:00-04:00",
  "caption": "Caption text, emoji and #hashtags (max 2,200 characters, 30 hashtags)",
  "images": ["1.jpg"]
}
```

Two optional extras:
- `"alt_text": "Description of the image for screen readers"`: single-image posts only, up to 1,000 characters.
- `"is_ai_generated": true`: adds Instagram's "AI info" label. Use it when the image was made with AI.

- Times need the time zone: `-04:00` in summer (EDT), `-05:00` in winter (EST). Clocks change on the first Sunday of November and the second Sunday of March. Check queue flags a wrong one.
- The poster checks every 15 minutes (:04, :19, :34, :49), and GitHub can start it late when it's busy. So an 11:00 post usually goes up around 11:04–11:30.
- After posting, it writes `result.json` (with the post link) next to the post, so it never posts twice. If Instagram rejects a post for a reason retrying won't fix (bad image, caption too long, account restricted, spam flag), it writes `result.json` with `"status": "failed"` and the reason instead. Fix the problem, delete that `result.json` and push to try again.
- Every push runs **Check queue**, which catches non-JPEG images, wrong shapes, missing time zones and long captions before posting day.

## Reels

A reel is a queue folder like any other, but the video doesn't go in the folder. Videos are too big for the repo (it would grow by gigabytes a year), so they go on a GitHub Release named `reels`, which has no size or download limits.

**One time:** repo › **Releases › Draft a new release** › tag `reels` › title `Reels` › tick **Set as a pre-release** › **Publish release**.

**For each reel:**
1. Name the video after its folder, e.g. `2026-11-05-gutter-tips.mp4`. It must be MP4 or MOV, H.264, 9:16, 3 seconds to 15 minutes, and under 300 MB. Phone exports are normally fine.
2. Repo › **Releases › Reels › Edit** (the pencil) › drag the video into the box › **Update release**.
3. Make the queue folder and push:
```
queue/
  2026-11-05-gutter-tips/
    post.json
    cover.jpg        ← optional cover image (JPEG); otherwise Instagram uses the first frame
```
```json
{
  "publish_at": "2026-11-05T09:00:00-05:00",
  "caption": "Caption text and #hashtags",
  "reel": true,
  "cover": "cover.jpg",
  "share_to_feed": true
}
```
- `cover` and `share_to_feed` are optional. `share_to_feed: false` keeps the reel in the Reels tab only.
- Upload the video **before** pushing the folder. Check queue fails if the video isn't on the release yet.
- Instagram can take a few minutes to process a video. If it isn't ready, the poster checks again on the next run (the folder gets a `container.json` meanwhile) instead of uploading again.

## Stories

Stories run on their own rotation from the `stories/` folder. See [stories/README.md](stories/README.md).
- Drop 1080×1920 JPEGs in `stories/` and push.
- The times are in `stories/config.json`, Connecticut time. The default is 8:30am, 12:30pm and 6:30pm.
- An image isn't repeated within 3 days (also in `config.json`), so keep about 9 images there to fill every slot.
- If Instagram flags the account, Stories pause themselves (a `stories/PAUSED` file says why). Delete that file to restart.

## When something goes wrong
- GitHub emails you when a run fails. The log says why in plain words.
- "token is expired or invalid": do step 4 again and replace `IG_ACCESS_TOKEN`.
- Limits: Meta's docs say 50 (in places 100) API posts per 24 hours. **Check Instagram token** shows the real number. Not a concern at our pace.
- GitHub pauses timers in repos with no activity for 60 days. Each posted result is a commit, so this only happens if nothing is queued for two months.
