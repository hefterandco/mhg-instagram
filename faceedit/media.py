"""ffprobe / ffmpeg helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(f"{tool} is not installed. On a Mac: brew install ffmpeg")
    return path


@dataclass
class Probe:
    path: Path
    width: int          # as displayed (rotation applied)
    height: int
    raw_width: int      # as stored in the file
    raw_height: int
    rotation: int       # degrees, as phones store it
    fps: float
    duration: float
    has_audio: bool


def probe(path: str | Path) -> Probe:
    need("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"Could not read {path}: {out.stderr.strip()[:300]}")
    info = json.loads(out.stdout)
    video = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if not video:
        raise SystemExit(f"{path} has no video stream")
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])

    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(round(float(sd["rotation"])))
    if not rotation and "rotate" in (video.get("tags") or {}):
        rotation = int(video["tags"]["rotate"])
    rw, rh = int(video["width"]), int(video["height"])
    w, h = (rh, rw) if abs(rotation) % 180 == 90 else (rw, rh)

    num, _, den = (video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    duration = float(video.get("duration") or info.get("format", {}).get("duration") or 0)
    return Probe(Path(path), w, h, rw, rh, rotation, fps or 30.0, duration, has_audio)


def run_ffmpeg(args: list[str], cwd: str | Path | None = None, quiet: bool = True) -> None:
    need("ffmpeg")
    cmd = ["ffmpeg", "-hide_banner", "-y"] + (["-loglevel", "error", "-stats"] if quiet else []) + args
    res = subprocess.run(cmd, cwd=cwd)
    if res.returncode != 0:
        raise SystemExit("ffmpeg failed (see the message above).")
