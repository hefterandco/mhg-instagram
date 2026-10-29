"""Turns a plan into the finished vertical video in one ffmpeg pass."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import broll as broll_mod
from .captions import build_ass
from .cards import endcard_png, title_png
from .config import FONTS
from .cuts import edited_length, edited_words, to_edited
from .media import probe, run_ffmpeg

XFADE = 0.35


def snap_to_edited(t: float, segments: list[dict]) -> float:
    """Like to_edited, but a moment that was cut snaps to the next kept moment."""
    hit = to_edited(t, segments)
    if hit is not None:
        return hit
    acc = 0.0
    for s in segments:
        if t < s["start"]:
            return acc
        acc += s["end"] - s["start"]
    return acc


def render(plan: dict, settings: dict, out: Path, keep_temp: bool = False) -> Path:
    o = settings["output"]
    W, H, FPS = o["width"], o["height"], o["fps"]
    src = probe(plan["source"])
    if not src.has_audio:
        raise SystemExit("This clip has no audio track, so there's nothing to cut to.")
    segs = plan["segments"]
    L = edited_length(segs)
    tmp = Path(tempfile.mkdtemp(prefix="faceedit-"))
    shutil.copytree(FONTS, tmp / "fonts")

    args: list[str] = ["-i", str(src.path)]
    n_in = 1
    g: list[str] = []

    # 1. Kept segments: trim, crop to 9:16 on the face, scale, join.
    n = len(segs)
    g.append(f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n)))
    g.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)))
    for i, s in enumerate(segs):
        x, y, cw, ch = s["crop"]
        d = s["end"] - s["start"]
        g.append(f"[vs{i}]trim=start={s['start']:.3f}:end={s['end']:.3f},setpts=PTS-STARTPTS,"
                 f"crop={cw}:{ch}:{x}:{y},scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS},format=yuv420p[v{i}]")
        g.append(f"[as{i}]atrim=start={s['start']:.3f}:end={s['end']:.3f},asetpts=PTS-STARTPTS,"
                 f"aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.012):.3f}:d=0.012[a{i}]")
    g.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vcat][acat]")
    v = "vcat"

    # 2. B-roll cutaways over the face video (your voice keeps going underneath).
    credits = []
    for m in plan.get("broll", []):
        m.setdefault("seconds", settings["broll"]["clip_seconds"])
    for w in broll_mod.fill_missing(plan.get("broll", []), settings["broll"]["local_dir"]):
        print(f"  note: {w}")
    for j, m in enumerate(plan.get("broll", [])):
        if not (m.get("file") or m.get("download")):
            continue
        path = broll_mod.local_path(m)
        clip = probe(path)
        T = snap_to_edited(m["at"], segs)
        dur = min(m["seconds"], L - T - 0.2)
        if dur < 0.8:
            continue
        offset = min(1.0, max(0.0, clip.duration - dur - 0.1))
        args += ["-i", str(path)]
        g.append(f"[{n_in}:v]trim=start={offset:.2f}:duration={dur:.2f},setpts=PTS-STARTPTS+{T:.3f}/TB,"
                 f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
                 f"format=yuv420p[b{j}]")
        g.append(f"[{v}][b{j}]overlay=eof_action=pass:enable='between(t,{T:.3f},{T + dur:.3f})'[vb{j}]")
        v = f"vb{j}"
        n_in += 1
        if m.get("source") == "pexels":
            credits.append(f"{m['search']}: video by {m.get('by') or 'unknown'} on Pexels {m.get('page', '')}")

    # 3. Hook title at the top for the first few seconds.
    if plan.get("title"):
        tc = settings["title"]
        secs = min(tc["seconds"], L)
        title_png(plan["title"], tc, W, H, tmp / "title.png")
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{secs:.2f}", "-i", "title.png"]
        g.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0:d=0.2:alpha=1,"
                 f"fade=t=out:st={max(0, secs - 0.4):.2f}:d=0.4:alpha=1[tt]")
        g.append(f"[{v}][tt]overlay=0:0:eof_action=pass:format=auto[vt]")
        v = "vt"
        n_in += 1

    # 4. Word-by-word captions.
    if plan.get("captions", True):
        words = edited_words(plan["words"], segs)
        (tmp / "captions.ass").write_text(build_ass(words, settings["captions"], W, H))
        g.append(f"[{v}]ass=captions.ass:fontsdir=fonts,format=yuv420p,settb=AVTB[vc]")
        v = "vc"

    # 5. Clean up the voice: rumble filter + Instagram loudness.
    g.append(f"[acat]highpass=f=80,loudnorm=I={o['loudness']}:TP=-1.5:LRA=11,"
             f"aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[an]")
    a = "an"

    # 6. End card, crossfaded in.
    ec = settings["endcard"]
    if plan.get("endcard", True) and ec["enabled"]:
        endcard_png(ec, W, H, tmp / "end.png")
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{ec['seconds']:.2f}", "-i", "end.png",
                 "-f", "lavfi", "-t", f"{ec['seconds']:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
        g.append(f"[{n_in}:v]format=yuv420p,fps={FPS},setsar=1,settb=AVTB[ve]")
        g.append(f"[{v}]settb=AVTB[vm]")
        g.append(f"[vm][ve]xfade=transition=fade:duration={XFADE}:offset={max(0, L - XFADE - 0.05):.3f}[vx]")
        g.append(f"[{a}][{n_in + 1}:a]acrossfade=d={XFADE}[ax]")
        v, a = "vx", "ax"
        n_in += 2

    (tmp / "graph.txt").write_text(";\n".join(g))
    out = out.resolve()
    args += ["-filter_complex_script", "graph.txt", "-map", f"[{v}]", "-map", f"[{a}]",
             "-c:v", "libx264", "-preset", o["preset"], "-crf", str(o["crf"]), "-pix_fmt", "yuv420p",
             "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    # Inputs given as absolute paths; cards, captions and fonts are relative to tmp.
    print(f"Rendering {out.name} ({L:.1f}s of you"
          f"{', ' + str(len(credits)) + ' stock cutaways' if credits else ''})...")
    run_ffmpeg(args, cwd=tmp)

    if credits:
        out.with_suffix(".credits.txt").write_text(
            "B-roll from Pexels (free to use; credit appreciated, e.g. 'B-roll: Pexels'):\n"
            + "\n".join(credits) + "\n")
    if keep_temp:
        print(f"Temp files kept in {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return out
