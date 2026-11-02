# insights/

Written by `poster/insights.py` (the **Collect Instagram insights** workflow, four times a day). Don't edit these by hand; the next run overwrites them.

| File | What's in it |
|---|---|
| `account.json` | `followers` and `media_count` by Connecticut date (the last reading of the day). `days` holds account reach, views, accounts engaged, interactions, likes, comments, saves, shares and link taps for each finished day; the last 3 days are re-read every run because Meta's numbers lag up to 48 hours. `insights_permission` is false until the token has the insights scope. |
| `posts.json` | Every feed post and Reel on the account, keyed by Instagram media ID. `folder` is the matching `queue/` folder, if it came from the queue. `like_count` and `comments_count` always fill in; `metrics` (reach, views, saves, shares, follows and so on) needs the insights scope. Refreshed every run for 30 days after posting, then weekly. `settling: true` means the post is under 48 hours old and its numbers are still coming in. |
| `stories.json` | Every Story caught while it was live, with its `stories/` file name. Meta deletes Story numbers after 24 hours, so the last reading before then is what stays. |

A `null` means Meta didn't give a number (not available yet, not available for this kind of post, or the account is under 100 followers). It is not a zero.

To see it as a dashboard, run `python tools/build_dashboard.py` and open the file it writes.

This repo is public, so these numbers are public too.
