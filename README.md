# MHG Instagram poster

Hands-off Instagram posting for My House Guardian.

Drop a finished post (JPEG + caption + time) into `queue/`, push, and GitHub publishes it to Instagram at that time. Free to run: GitHub Actions on a timer plus Instagram's own API. No paid services.

- **Setup:** [SETUP.md](SETUP.md), with every key listed fill-in-the-blank.
- **What's queued:** the `queue/` folder; `result.json` in a folder means it's been posted.
- **Check the queue locally:** `python poster/queue_check.py`
- **Turn a canvas artboard into a post image:** `node tools/render_artboard.js Post.dc.html queue/<folder>/1.jpg <fontsDir>`

| Workflow | When | What |
|---|---|---|
| Post to Instagram | hourly at :07, or by hand | Publishes due posts; dry run by default when run by hand |
| Refresh Instagram token | Mondays | Keeps the 60-day token alive |
| Check Instagram token | by hand | Confirms the token and shows the account |
| Check queue | every push | Catches bad images or captions early |
