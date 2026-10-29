# Stories rotation

Drop 1080×1920 JPEGs (9:16) in this folder and push. That's it.

- At each time in `config.json` (Connecticut time), the poster posts one image here as a Story.
- New images go first. After that, it reuses whichever image has gone longest without being posted.
- An image isn't repeated within `min_days_between_repeats` days. If every image was used too recently, that time slot is skipped. Keep about (times per day × days) images here to never skip: 3 × 7 = **21**.
- To take an image out of the rotation, delete it. To change the schedule, edit `config.json`.
- `history.json` is the log of what posted when. The poster writes it; don't edit it.
- If Instagram flags the account, the rotation stops itself and writes a `PAUSED` file explaining why. Sort it out in the Instagram app, then delete `PAUSED` to restart.
- Story limits: no link stickers, polls or location tags through the API. Post those by hand.
