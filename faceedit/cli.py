"""faceedit: turns a raw face-to-camera clip into a finished My House Guardian Reel.

  python -m faceedit edit clip.mov --title "Clean your gutters twice"
      plan + render in one go -> clip.edit.mp4

  python -m faceedit plan clip.mov --title "..."
      transcribe, pick cuts, framing and B-roll -> clip.plan.json (edit it if you like)
  python -m faceedit render clip.plan.json
      build the video from the (edited) plan -> clip.edit.mp4

  python -m faceedit queue clip.edit.mp4 --at "2026-11-05 09:00"
      upload to the "reels" release and create queue/2026-11-05-clip/ (caption left for you)
  python -m faceedit edit clip.mov --title "..." --queue-at "2026-11-05 09:00"
      edit, then queue in one go
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_dotenv, load_settings
from .queue import queue_reel


def make_plan(src: Path, args, settings: dict) -> dict:
    from . import broll, cuts, reframe
    from .media import probe
    from .transcribe import load_words, transcribe

    p = probe(src)
    cc, oc = settings["cuts"], settings["output"]
    if args.transcript:
        words = load_words(args.transcript)
    else:
        tc = settings["transcribe"]
        words = transcribe(src, args.model or tc["model"], tc["language"])
    if not words:
        raise SystemExit("No speech found in this clip.")
    cuts.mark_fillers(words, cc["fillers"])
    cuts.apply_corrections(words, settings["captions"]["corrections"])
    retakes = cuts.mark_retakes(words) if cc.get("retakes", True) and not args.no_cuts else []

    tail = 0.4 if (settings["endcard"]["enabled"] and not args.no_endcard) else 0.1
    if args.no_cuts:
        segs = [{"start": 0.0, "end": round(p.duration, 3)}]
    else:
        segs = cuts.keep_segments(words, p.duration, cc["max_pause"], cc["pad_before"], cc["pad_after"], tail)
    hidden = []
    if cc.get("hidden_fillers", True) and not args.no_cuts:
        from .fillers import hidden_fillers
        hidden = hidden_fillers(src, words)
        segs = cuts.remove_spans(segs, hidden)

    print("Finding your face...")
    faces = [] if args.no_reframe else reframe.detect_faces(p)
    punch = 1.0 if args.no_punch else cc["punch_in"]
    reframe.plan_crops(segs, faces, p, oc["width"], oc["height"], punch, settings["reframe"]["face_height"])

    bc = settings["broll"]
    moments, warnings = [], []
    if bc["enabled"] and not args.no_broll:
        topics = broll.load_topics(args.topics)
        moments, warnings = broll.choose(words, segs, topics, bc, args.broll_dir or bc["local_dir"])

    plan = {
        "source": str(src.resolve()),
        "title": args.title or "",
        "captions": not args.no_captions,
        "endcard": not args.no_endcard,
        "segments": segs,
        "hidden_fillers": hidden,
        "broll": moments,
        "words": words,
    }
    fillers = sum(1 for w in words if w.get("filler"))
    new_len = cuts.edited_length(segs)
    print(f"{p.duration:.1f}s raw -> {new_len:.1f}s edited: {len(segs) - 1} cuts, "
          f"{fillers} fillers out (+{len(hidden)} heard but not transcribed), "
          f"{len(retakes)} retakes dropped, face found in {len(faces)} samples, "
          f"{len(moments)} B-roll cutaways")
    for r in retakes:
        print(f"  retake dropped (the later take is kept): \"{r}\"")
    for a, b in hidden:
        print(f"  cut a sound with no word at {a:.2f}-{b:.2f}s (likely um/uh)")
    for m in moments:
        print(f"  B-roll at {m['at']:.1f}s (\"{m['said']}\"): {m['search']} [{m.get('source')}]")
    for w in warnings:
        print(f"  note: {w}")
    if not faces and not args.no_reframe:
        print("  note: no face found, so the crop is centered.")
    return plan


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="faceedit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def plan_opts(sp):
        sp.add_argument("clip", type=Path)
        sp.add_argument("--title", help="hook text shown at the top for the first few seconds")
        sp.add_argument("--model", help="Whisper model, e.g. small.en, medium.en")
        sp.add_argument("--transcript", help="reuse a saved transcript or plan instead of Whisper")
        sp.add_argument("--topics", help="extra B-roll topics file (same format as broll_topics.toml)")
        sp.add_argument("--broll-dir", help="folder of your own clips to use before Pexels")
        for flag in ("cuts", "reframe", "punch", "broll", "captions", "endcard"):
            sp.add_argument(f"--no-{flag}", action="store_true")
        sp.add_argument("--settings", help="alternate settings file")

    def queue_opts(sp, flag):
        sp.add_argument(flag, metavar='"YYYY-MM-DD HH:MM"', help="when to post, Connecticut time")
        sp.add_argument("--slug", help="short name for the queue folder (default: from the file name)")
        sp.add_argument("--cover", type=Path, help="optional JPEG cover image")
        sp.add_argument("--replace", action="store_true", help="overwrite an existing upload and folder")

    plan_opts(sp_plan := sub.add_parser("plan", help="make an editable plan"))
    plan_opts(sp_edit := sub.add_parser("edit", help="plan and render in one step"))
    sp_edit.add_argument("-o", "--out", type=Path)
    sp_edit.add_argument("--keep-temp", action="store_true")
    queue_opts(sp_edit, "--queue-at")
    sp_r = sub.add_parser("render", help="render a plan")
    sp_r.add_argument("plan", type=Path)
    sp_r.add_argument("-o", "--out", type=Path)
    sp_r.add_argument("--settings")
    sp_r.add_argument("--keep-temp", action="store_true")
    queue_opts(sp_r, "--queue-at")
    sp_q = sub.add_parser("queue", help="upload a finished Reel and create its queue folder")
    sp_q.add_argument("video", type=Path)
    queue_opts(sp_q, "--at")
    args = ap.parse_args(argv)

    if args.cmd == "queue":
        if not args.at:
            raise SystemExit('Say when to post: --at "2026-11-05 09:00"')
        queue_reel(args.video, args.at, args.slug, args.cover, args.replace)
        return 0

    # Imported here so `queue` works without the editing tools (Whisper, OpenCV, ffmpeg) installed.
    from .render import render

    settings = load_settings(args.settings)
    if args.cmd in ("plan", "edit"):
        if not args.clip.exists():
            raise SystemExit(f"Can't find {args.clip}")
        plan = make_plan(args.clip, args, settings)
        plan_path = args.clip.with_suffix(".plan.json")
        plan_path.write_text(json.dumps(plan, indent=1))
        print(f"Plan saved: {plan_path}")
        if args.cmd == "plan":
            return 0
        out = args.out or args.clip.with_name(args.clip.stem + ".edit.mp4")
    else:
        plan = json.loads(args.plan.read_text())
        out = args.out or Path(plan["source"]).with_name(Path(plan["source"]).stem + ".edit.mp4")
    done = render(plan, settings, out, keep_temp=args.keep_temp)
    print(f"Done: {done}")
    if getattr(args, "queue_at", None):
        queue_reel(Path(done), args.queue_at, args.slug, args.cover, args.replace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
