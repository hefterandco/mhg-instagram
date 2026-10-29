"""Finds fillers Whisper didn't write down.

Whisper often leaves "um" and "uh" out of its transcript even when told to keep
them, so they survive the cut hidden in the gaps between words. This listens to
the gaps: a stretch that is loud and voiced (has a pitch, like a vowel) but has
no word on it is treated as a filler and cut. Breaths are unvoiced, so they stay
and the speech still sounds human.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .media import need

RATE = 16000
HOP = 160          # 10 ms
FRAME = 640        # 40 ms analysis window
EDGE = 0.06        # ignore this much next to each word (Whisper's word times are loose)


def _frames(path: str | Path):
    import numpy as np
    need("ffmpeg")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1",
                          "-ar", str(RATE), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = max(0, (len(a) - FRAME) // HOP)
    return np.lib.stride_tricks.sliding_window_view(a, FRAME)[::HOP][:n] if n else a[:0].reshape(0, FRAME)


def _voiced(frames) -> tuple:
    """Per 10 ms: loudness in dB and whether the sound has a pitch (75-300 Hz)."""
    import numpy as np
    x = frames - frames.mean(1, keepdims=True)
    db = 10 * np.log10((x ** 2).mean(1) + 1e-10)
    spec = np.fft.rfft(x * np.hanning(FRAME), 2 * FRAME)
    ac = np.fft.irfft(np.abs(spec) ** 2)[:, :FRAME]
    lo, hi = RATE // 300, RATE // 75
    pitch = ac[:, lo:hi].max(1) / (ac[:, 0] + 1e-10)
    return db, pitch


def hidden_fillers(path: str | Path, words: list[dict], min_len: float = 0.15) -> list[tuple[float, float]]:
    """(start, end) spans in the raw clip that sound like an untranscribed um/uh."""
    import numpy as np
    spoken = [w for w in words if not w.get("filler")]
    if len(spoken) < 2:
        return []
    db, pitch = _voiced(_frames(path))
    t = lambda sec: min(len(db), max(0, int(sec * RATE / HOP)))
    level = np.median(np.concatenate([db[t(w["s"]):t(w["e"])] for w in spoken]) if spoken else db)
    floor = np.percentile(db, 10)
    loud = db > floor + 0.5 * (level - floor)
    voiced = loud & (pitch > 0.5)
    spans = []
    for w1, w2 in zip(spoken, spoken[1:]):
        a, b = t(w1["e"] + EDGE), t(w2["s"] - EDGE)
        run_start = None
        for i in range(a, b + 1):
            on = i < b and voiced[i]
            if on and run_start is None:
                run_start = i
            elif not on and run_start is not None:
                if (i - run_start) * HOP / RATE >= min_len:
                    spans.append((round(run_start * HOP / RATE - 0.03, 3), round(i * HOP / RATE + 0.03, 3)))
                run_start = None
    return spans
