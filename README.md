# MHG Instagram poster

Hands-off Instagram posting for My House Guardian.

Drop a finished post (JPEG + caption + time) into `queue/`, push, and GitHub publishes it to Instagram at that time. Reels work the same way, with the video on the `reels` release, and Stories rotate automatically from `stories/`. Free to run: GitHub Actions on a timer plus Instagram's own API. No paid services.

- **Setup:** [SETUP.md](SETUP.md), with every key listed fill-in-the-blank.
- **What's queued:** the `queue/` folder. A `result.json` in a folder means it's been handled: `published`, `missed` (too late) or `failed` (a problem retrying won't fix; the file says why, and deleting it tries again).
- **Check the queue locally:** `python poster/queue_check.py`
- **Edit a face-to-camera video into a Reel (captions, cuts, B-roll, end card):** `python3 -m faceedit edit clip.mov --title "..."`. See [faceedit/README.md](faceedit/README.md)
- **Turn a canvas artboard into a post image:** `node tools/render_artboard.js Post.dc.html queue/<folder>/1.jpg <fontsDir>`

| Workflow | When | What |
|---|---|---|
| Post to Instagram | every 15 minutes, or by hand | Publishes due posts, reels and Stories; dry run by default when run by hand |
| Refresh Instagram token | Mondays | Keeps the 60-day token alive |
| Check Instagram token | by hand | Confirms the token and shows the account |
| Check queue | every push | Catches bad images, captions, time zones, missing reel videos and wrong-shaped Stories early |
| Test video hosting | by hand, once | Checks Instagram can fetch a reel from GitHub; never posts |
