# faceedit: face-to-camera Reels editor

Turns a raw clip of you talking to the camera into a finished vertical Reel for My House Guardian. It runs on your laptop for free. B-roll comes from your own clips in `~/Movies/MHG-broll`. Pexels stock footage is optional and currently skipped: Pexels paused new API keys, so `PEXELS_API_KEY` is left blank.

What it does to a clip:

1. **Transcribes** it word by word with Whisper, running locally.
2. **Cuts dead air and fillers.** Pauses longer than 0.3s are cut down to about a third of a second, so the pacing is tight without sounding rushed. "Um" and "uh" are cut, including ones Whisper didn't write down: faceedit listens for voiced sounds between words that have no word on them. Silent breaths stay, so it still sounds human.
3. **Drops retakes.** If you restart a line ("My House Guardian gives you… / My House Guardian gives your family…"), the earlier take is removed and the later one kept. The plan lists what it dropped. To bring one back, remove `"retake": true` from those words in the plan.
4. **Reframes** to 9:16 (1080×1920) on your face, and holds the framing steady across cuts unless you actually move. Every other cut steps in 10% closer, so jump cuts read as a deliberate camera change. Within each shot there's a slow, smooth push-in (about 4%) to keep the frame alive. Audio joins are softened so cuts don't click or clip a breath.
5. **Adds B-roll that shows the business.** Cutaways show what My House Guardian takes off the homeowner's plate: the house manager, to-do visits, the partner bundles, the house record. Those come only from **your own clips** in `~/Movies/MHG-broll`, because stock can't show our service honestly. Free Pixabay stock (`PIXABAY_API_KEY` in `.env`) fills only family-life and season moments (foliage, snowfall, lights), never houses or streets (they aren't Fairfield), and never anything tagged as a scare, security, senior care, off-region or a brand (`avoid_tags` in `faceedit.toml`). The rules and trigger words are in `broll_topics.toml`. After `plan`, check the **B-roll review sheet** (`<video>.broll.jpg`): each moment's candidates side by side, plus the clips still to film. Swap or drop picks with `.venv/bin/python -m faceedit broll <plan> 2=3 1=0`, then render.
6. **Adds captions** in Nunito Sans, word by word. Each line pops in, and the word being spoken is clay and slightly bigger. "My Home Guardian" is auto-corrected.
7. **Adds a hook title** (optional) at the top for the first 3 seconds, in Fraunces on cream. The house logo then sits in the top-right corner for the rest of the video.
8. **Adds an end card**: the house mark, "Your House, Our Problems", @myhouseguardian, the website, your email and the phone number.
9. **Fixes the audio** to Instagram loudness (−14 LUFS) and filters out low rumble.

## One-time setup (Mac)

Needs Homebrew (brew.sh). Then, in Terminal:

```bash
brew install ffmpeg-full python@3.12
brew unlink ffmpeg 2>/dev/null; brew link --force ffmpeg-full   # plain "ffmpeg" lacks the caption filter (libass)
cd ~/Desktop/mhg-instagram
/opt/homebrew/bin/python3.12 -m venv .venv                     # faceedit's own Python, kept in the repo folder (not committed)
.venv/bin/pip install -r faceedit/requirements.txt
cp .env.example .env        # PEXELS_API_KEY can stay blank (see below)
```

Run faceedit from the repo folder with `.venv/bin/python -m faceedit …`, as in the examples below. Check the setup with `.venv/bin/python faceedit/tests/test_core.py`.

Why `ffmpeg-full`: Homebrew's standard `ffmpeg` no longer includes libass, which draws the captions (the `ass` filter). faceedit needs ffmpeg 7 or newer.

**B-roll:** put your own clips in `~/Movies/MHG-broll`, named by what's in them, e.g. `gutter-cleaning-westport.mp4`. When you say a matching word, faceedit cuts to that clip. That folder is set as `local_dir` in `faceedit.toml`.

**PEXELS_API_KEY** (optional, skipped for now): Pexels has paused new API keys. If they reopen, get a free key at https://www.pexels.com/api/ and paste it into `.env` to add stock B-roll when your own clips don't match. Without it everything works; edits just print a note that no stock B-roll was pulled.

The first transcription downloads the Whisper model once (`small.en`, about 480 MB). After that it runs offline.

## Everyday use

```bash
.venv/bin/python -m faceedit edit ~/Movies/gutters.mov --title "Your gutters are full. Now what?"
```

→ `gutters.edit.mp4` next to the original, plus `gutters.edit.credits.txt` listing the Pexels clips used.

### Review before rendering (optional)

```bash
.venv/bin/python -m faceedit plan ~/Movies/gutters.mov --title "..."   # writes gutters.plan.json
# open the plan and change anything:
#   "words"    fix a misheard caption word
#   "segments" adjust or delete a cut
#   "broll"    delete a cutaway, or add one: {"at": 12.5, "search": "snow plow driveway"}
#              ("at" = seconds into the ORIGINAL clip)
.venv/bin/python -m faceedit render ~/Movies/gutters.plan.json
```

Re-rendering a plan doesn't re-transcribe, so changes are quick.

### Switches

| Flag | Does |
|---|---|
| `--title "..."` | hook text at the top |
| `--no-broll` / `--no-captions` / `--no-endcard` | skip that part |
| `--no-cuts` | keep every pause |
| `--no-punch` | no zoom on jump cuts |
| `--no-reframe` | center crop, no face tracking |
| `--broll-dir ~/Movies/MHG-broll` | your own clips first; name files by content, e.g. `gutter-cleaning-westport.mp4` |
| `--model medium.en` | more accurate transcription, slower |
| `--topics mytopics.toml` | extra keyword → B-roll mappings for this video |

## Send it to Instagram

Add `--queue-at` with the posting time (Connecticut time) and the finished video goes straight into the auto-poster:

```bash
.venv/bin/python -m faceedit edit ~/Movies/gutters.mov --title "Your gutters are full. Now what?" --queue-at "2026-11-05 09:00"
```

Or queue a video that's already finished (from faceedit or edited anywhere else):

```bash
.venv/bin/python -m faceedit queue ~/Movies/gutters.edit.mp4 --at "2026-11-05 09:00"
```

Either way it:
1. Uploads the video to the `reels` GitHub Release as `2026-11-05-gutters.mp4`, not into the repo.
2. Creates `queue/2026-11-05-gutters/post.json` with the time and the caption **`WRITE THE CAPTION HERE`**.

Then open that `post.json`, replace the placeholder with your caption, and commit and push. **Until the placeholder is replaced, the post is a draft and never publishes**, even if its time passes.

| Flag | Does |
|---|---|
| `--slug gutter-tips` | folder and file name, instead of the video's file name |
| `--cover thumb.jpg` | JPEG cover image instead of the first frame |
| `--replace` | upload over an existing video and folder with the same name |

It needs the `reels` release to exist (SETUP.md › Reels) and the GitHub login your Mac saved when you last pushed. Or put a token in `.env` as `GITHUB_TOKEN`. The `queue` command runs without Whisper, OpenCV or ffmpeg installed.

## Tuning

- `faceedit/faceedit.toml` holds caption size, colors, position and pop, cut tightness, filler and retake removal, zoom and push-in, B-roll frequency, the title look, the corner logo and the end card text.
- `faceedit/broll_topics.toml` maps what you say to the B-roll it searches for. Topics nearer the top take priority. Add your own.

## Notes

- The free Pexels license allows commercial use and doesn't require credit. Crediting "B-roll: Pexels" is appreciated, and the credits file has the names.
- Shoot vertical at 1080p or 4K and keep your face in the upper half. A landscape clip also works, since it gets cropped around your face.
- Tests: `.venv/bin/python faceedit/tests/test_core.py`
