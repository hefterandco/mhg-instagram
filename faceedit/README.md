# faceedit: face-to-camera Reels editor

Turns a raw clip of you talking to the camera into a finished vertical Reel for My House Guardian. It runs on your laptop for free. B-roll comes from your own clips in `~/Movies/MHG-broll`. When none of your clips match, it pulls free stock footage from Pixabay (needs a free `PIXABAY_API_KEY`). Pexels also works if you ever get a key, but they've paused new ones.

What it does to a clip:

1. **Transcribes** it word by word with Whisper, running locally.
2. **Cuts dead air and fillers.** Pauses longer than 0.3s are cut down to about a third of a second, so the pacing is tight without sounding rushed. "Um" and "uh" are cut, including ones Whisper didn't write down: faceedit listens for voiced sounds between words that have no word on them. Silent breaths stay, so it still sounds human.
3. **Drops retakes.** If you restart a line ("My House Guardian gives you… / My House Guardian gives your family…"), the earlier take is removed and the later one kept. The plan lists what it dropped. To bring one back, remove `"retake": true` from those words in the plan.
4. **Reframes** to 9:16 (1080×1920) on your face, and holds the framing steady across cuts unless you actually move. Every other cut steps in 10% closer, so jump cuts read as a deliberate camera change. Within each shot there's a slow, smooth push-in (about 4%) to keep the frame alive. Audio joins are softened so cuts don't click or clip a breath.
5. **Adds B-roll.** When you say "gutters", "basement", "snow", "dryer vent" and so on, a matching 2.4s cutaway plays over the video while your voice keeps going. Clips come from your own folder first, then Pixabay stock.
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
cp .env.example .env        # then fill in PIXABAY_API_KEY (free, see below)
```

Run faceedit from the repo folder with `.venv/bin/python -m faceedit …`, as in the examples below. Check the setup with `.venv/bin/python faceedit/tests/test_core.py`.

Why `ffmpeg-full`: Homebrew's standard `ffmpeg` no longer includes libass, which draws the captions (the `ass` filter). faceedit needs ffmpeg 7 or newer.

**B-roll:** put your own clips in `~/Movies/MHG-broll`, named by what's in them: `gutter.mp4`, `Leaves 2.mov`, `dryer-vent.mp4`, or keep the phone's `IMG_4821.MOV` name inside a folder like `MHG-broll/snow/`. Singular or plural doesn't matter. When you say a matching word (see `broll_topics.toml`), faceedit cuts to that clip. If nothing matches, the edit prints which words had no clip so you know what to film. That folder is set as `local_dir` in `faceedit.toml`.

**PIXABAY_API_KEY** (free, no card): sign up at pixabay.com, then open https://pixabay.com/api/docs/ while logged in. Your key is shown in the "Parameters" table next to `key`. Paste it into `.env`. Stock clips are used only when your own folder has no match. Pixabay footage is mostly landscape, so it's cropped to vertical; faceedit takes the 4K version when it's under 80 MB so the crop stays sharp. Clips where people are the subject are picked last, but still look over any stock clip with a recognizable face before you post. Searches are cached for 24 hours (Pixabay requires it) and downloads are kept in `~/.cache/mhg-faceedit`.

**PEXELS_API_KEY** (optional, skipped for now): Pexels has paused new API keys. If they reopen, get a free key at https://www.pexels.com/api/ and paste it into `.env` to add stock B-roll when your own clips don't match. Without it everything works; edits just print a note that no stock B-roll was pulled.

The first transcription downloads the Whisper model once (`small.en`, about 480 MB). After that it runs offline.

## Everyday use

```bash
.venv/bin/python -m faceedit edit ~/Movies/gutters.mov --title "Your gutters are full. Now what?"
```

→ `gutters.edit.mp4` next to the original, plus `gutters.edit.credits.txt` listing any stock clips used.

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
| `--broll-dir ~/Movies/MHG-broll` | your own clips first; name files by content, e.g. `gutter.mp4` |
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

- Pixabay's Content License allows commercial use and doesn't require credit ("B-roll: Pixabay" is appreciated; the credits file has names and links). It forbids misleading use and using recognizable trademarks or brands to sell goods or services, so skip clips with visible logos or a recognizable person.
- Shoot vertical at 1080p or 4K and keep your face in the upper half. A landscape clip also works, since it gets cropped around your face.
- Tests: `.venv/bin/python faceedit/tests/test_core.py`
