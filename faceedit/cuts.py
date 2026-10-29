"""Decides what to keep: drops long pauses and filler words, and maps times
from the raw clip onto the edited timeline."""
from __future__ import annotations

import re

_PUNCT = re.compile(r"[^\w'-]+")


def norm(word: str) -> str:
    return _PUNCT.sub("", word.lower()).strip("-'")


def mark_fillers(words: list[dict], fillers: list[str]) -> None:
    fset = {f.lower() for f in fillers}
    for w in words:
        w["filler"] = norm(w["w"]) in fset


def apply_corrections(words: list[dict], corrections: list[list[str]]) -> None:
    """Fixes multi-word mishearings in place, e.g. "my home guardian" -> "My House Guardian"."""
    for wrong, right in corrections:
        wrong_toks, right_toks = wrong.lower().split(), right.split()
        n = len(wrong_toks)
        if n != len(right_toks):
            continue
        i = 0
        while i <= len(words) - n:
            if [norm(words[i + k]["w"]) for k in range(n)] == wrong_toks:
                for k in range(n):
                    tail = re.search(r"[^\w']*$", words[i + k]["w"]).group(0)
                    words[i + k]["w"] = right_toks[k] + tail
                i += n
            else:
                i += 1


def phrases(words: list[dict], gap: float = 0.6) -> list[list[int]]:
    """Word indexes grouped into phrases: split at end punctuation or a pause."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and w["s"] - words[cur[-1]]["e"] > gap:
            out.append(cur)
            cur = []
        cur.append(i)
        if re.search(r"[.?!]$", w["w"]):
            out.append(cur)
            cur = []
    return out + ([cur] if cur else [])


def mark_retakes(words: list[dict], lead: int = 5, min_match: int = 4, window: float = 15.0) -> list[str]:
    """Marks a phrase as a retake when a phrase starting soon after opens with
    (nearly) the same words, i.e. a line restarted after a stumble. The later,
    usually cleaner, take is kept. Returns the dropped phrases' text."""
    sub = [w for w in words if not w.get("filler")]
    groups = phrases(sub)
    dropped = []
    for gi, g in enumerate(groups):
        if len(g) < lead:
            continue
        head = [norm(sub[k]["w"]) for k in g[:lead]]
        for later in groups[gi + 1:]:
            if sub[later[0]]["s"] - sub[g[0]]["s"] > window:
                break
            if len(later) >= lead and sum(a == norm(sub[k]["w"]) for a, k in zip(head, later[:lead])) >= min_match:
                for k in g:
                    sub[k]["retake"] = True
                dropped.append(" ".join(sub[k]["w"] for k in g))
                break
    return dropped


def remove_spans(segments: list[dict], spans: list[tuple[float, float]], min_len: float = 0.15) -> list[dict]:
    """Cuts the given (start, end) spans out of the kept segments, e.g. hidden fillers."""
    out = []
    for seg in segments:
        pieces = [(seg["start"], seg["end"])]
        for a, b in spans:
            pieces = [p for s, e in pieces
                      for p in ([(s, e)] if b <= s or a >= e else [(s, a), (b, e)]) if p[1] > p[0]]
        out += [{"start": round(s, 3), "end": round(e, 3)} for s, e in pieces if e - s >= min_len]
    return out


def keep_segments(words: list[dict], duration: float, max_pause: float,
                  pad_before: float, pad_after: float, tail: float = 0.0) -> list[dict]:
    spoken = [w for w in words if not (w.get("filler") or w.get("retake"))]
    if not spoken:
        return [{"start": 0.0, "end": round(duration, 3)}]
    spans = []
    for w in spoken:
        s, e = max(0.0, w["s"] - pad_before), min(duration, w["e"] + pad_after)
        if spans and s - spans[-1][1] <= max_pause:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    spans[-1][1] = min(duration, spans[-1][1] + tail)
    return [{"start": round(s, 3), "end": round(e, 3)} for s, e in spans if e - s >= 0.15]


def edited_length(segments: list[dict]) -> float:
    return sum(s["end"] - s["start"] for s in segments)


def to_edited(t: float, segments: list[dict]) -> float | None:
    """Raw-clip time -> edited time. None if that moment was cut."""
    acc = 0.0
    for s in segments:
        if t < s["start"]:
            return None
        if t <= s["end"]:
            return acc + (t - s["start"])
        acc += s["end"] - s["start"]
    return None


def edited_words(words: list[dict], segments: list[dict]) -> list[dict]:
    """Spoken words that survive the edit, with edited-timeline times."""
    out = []
    for w in words:
        if w.get("filler") or w.get("retake"):
            continue
        mid = (w["s"] + w["e"]) / 2
        if to_edited(mid, segments) is None:
            continue
        s = to_edited(max(w["s"], _seg_of(mid, segments)["start"]), segments)
        e = to_edited(min(w["e"], _seg_of(mid, segments)["end"]), segments)
        out.append({"w": w["w"], "s": s, "e": max(e, s + 0.05), "raw_s": w["s"]})
    return out


def _seg_of(t: float, segments: list[dict]) -> dict:
    return next(s for s in segments if s["start"] <= t <= s["end"])
