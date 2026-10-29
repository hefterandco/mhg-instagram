# faceedit: face-to-camera Reels editor

Turns a raw clip of you talking to the camera into a finished vertical Reel for My House Guardian. It runs on your laptop for free. The only outside service is Pexels, for free stock B-roll.

What it does to a clip:

1. **Transcribes** it word by word with Whisper, running locally.
2. **Cuts** pauses longer than 0.3s and fillers ("um", "uh"), so the pacing is tight but still sounds like you.
3. **Reframes** to 9:16 (1080×1920) centered on your face. It punches in slightly on every other jump cut.
4. **Adds B-roll.** When you say "gutters", "basement", "snow", "dryer vent" and so on, a matching 2.4s cutaway plays over the video while your voice keeps going. Clips come from your own folder first, then from Pexels.
5. **Adds captions** in Nunito Sans, word by word, with the word being spoken in clay. "My Home Guardian" is auto-corrected.
6. **Adds a hook title** (optional) at the top for the first 3 seconds, in Fraunces on cream.
7. **Adds an end card**: the house mark, "Your House, Our Problems", @myhouseguardian, the website and the phone number.
8. **Fixes the audio** to Instagram loudness (−14 LUFS) and filters out low rumble.

## One-time setup (Mac)

```bash
brew install ffmpeg
cd mhg-instagram
pip3 install -r faceedit/requirements.txt
cp .env.example .env        # then fill in PEXELS_API_KEY (free, see below)
```

**PEXELS_API_KEY** (free, no card): sign up at pexels.com, go to https://www.pexels.com/api/ and click "Your API Key". Paste it into `.env`. Without the key everything else still works, and the video just has no stock B-roll.

The first transcription downloads the Whisper model once (`small.en`, about 480 MB). After that it runs offline.

## Everyday use

```bash
python3 -m faceedit edit ~/Movies/gutters.mov --title "Your gutters are full. Now what?"
```

→ `gutters.edit.mp4` next to the original, plus `gutters.edit.credits.txt` listing the Pexels clips used.

### Review before rendering (optional)

```bash
python3 -m faceedit plan ~/Movies/gutters.mov --title "..."   # writes gutters.plan.json
# open the plan and change anything:
#   "words"    fix a misheard caption word
#   "segments" adjust or delete a cut
#   "broll"    delete a cutaway, or add one: {"at": 12.5, "search": "snow plow driveway"}
#              ("at" = seconds into the ORIGINAL clip)
python3 -m faceedit render ~/Movies/gutters.plan.json
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

## Tuning

- `faceedit/faceedit.toml` holds caption size, colors and position, cut tightness, B-roll frequency, the title look and the end card text.
- `faceedit/broll_topics.toml` maps what you say to the B-roll it searches for. Topics nearer the top take priority. Add your own.

## Notes

- The free Pexels license allows commercial use and doesn't require credit. Crediting "B-roll: Pexels" is appreciated, and the credits file has the names.
- Shoot vertical at 1080p or 4K and keep your face in the upper half. A landscape clip also works, since it gets cropped around your face.
- Tests: `python3 faceedit/tests/test_core.py`
