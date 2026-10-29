"""Picks B-roll moments from what you say, and fetches matching clips.

Sources, in order: your own clips folder ([broll] local_dir, ~/Movies/MHG-broll),
matched by file name, then Pexels stock video if PEXELS_API_KEY is set.
"""
from __future__ import annotations

import json
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import PKG, cache_dir, secret
from .cuts import edited_length, norm, to_edited

UA = "mhg-faceedit/1.0 (+https://myhouseguardian.com)"
# Saying the company name shouldn't trigger the generic "house" B-roll.
IGNORE = [["my", "house", "guardian"], ["my", "house", "guardian's"]]
VIDEO_EXT = {".mp4", ".mov", ".m4v"}


def load_topics(extra: str | Path | None = None) -> list[dict]:
    files = ([Path(extra)] if extra else []) + [PKG / "broll_topics.toml"]
    topics = []
    for f in files:
        with open(f, "rb") as fh:
            topics += tomllib.load(fh).get("topic", [])
    for t in topics:
        t["_phrases"] = sorted(([p.lower().split() for p in t["say"]]), key=len, reverse=True)
    return topics


def choose(words: list[dict], segments: list[dict], topics: list[dict], cfg: dict,
           local_dir: str = "") -> tuple[list[dict], list[str]]:
    """Picks cutaway moments from spoken keywords and finds a clip for each.

    Specific topics (earlier in broll_topics.toml) win over generic ones like
    "house". A moment with no clip available gives its slot to the next one.
    Returned "at" times are raw-clip times, so the plan stays readable.
    """
    total = edited_length(segments)
    dur = cfg["clip_seconds"]
    budget = max(0, int(total // cfg["seconds_per_clip"]))
    from .captions import join_hyphens
    spoken = join_hyphens([w for w in words if not (w.get("filler") or w.get("retake"))])
    toks = [norm(w["w"]) for w in spoken]
    for i in range(len(toks)):
        for name in IGNORE:
            if toks[i:i + len(name)] == name:
                toks[i:i + len(name)] = [""] * len(name)

    hits = []
    for i in range(len(spoken)):
        for rank, t in enumerate(topics):
            phrase = next((p for p in t["_phrases"] if toks[i:i + len(p)] == p), None)
            if phrase:
                hits.append((rank, i, t, " ".join(spoken[k]["w"] for k in range(i, i + len(phrase)))))
                break

    finder = _Finder(local_dir)
    picked, tried = [], set()
    for rank, i, t, said in sorted(hits, key=lambda h: h[:2]):
        if len(picked) >= budget:
            break
        if t["search"] in tried:
            continue
        at = to_edited(spoken[i]["s"], segments)
        if at is None:
            continue
        at = max(0.0, at - 0.1)
        if at < cfg["protect_start"] or at + dur > total - cfg["protect_end"]:
            continue
        if any(abs(at - p["_t"]) < dur + cfg["min_gap"] for p in picked):
            continue
        tried.add(t["search"])
        m = {"_t": at, "at": round(spoken[i]["s"] - 0.1, 3), "seconds": dur,
             "said": said, "search": t["search"], "keywords": t["say"]}
        if finder.fill(m):
            picked.append(m)
    picked.sort(key=lambda p: p["_t"])
    for p in picked:
        p.pop("_t")
    return picked, finder.report()


def fill_missing(moments: list[dict], local_dir: str = "") -> list[str]:
    """Finds clips for hand-added plan entries that only have a "search"."""
    missing = [m for m in moments if not (m.get("file") or m.get("download"))]
    if not missing:
        return []
    finder = _Finder(local_dir)
    for m in missing:
        finder.fill(m)
    return finder.report()


# ---------------------------------------------------------------- sources

class _Finder:
    def __init__(self, local_dir: str = ""):
        self.key = secret("PEXELS_API_KEY")
        self.label = local_dir
        self.local: list[Path] = []
        self.used: set = set()
        self.warnings: list[str] = []
        self.misses: list[str] = []
        folder = Path(local_dir).expanduser() if local_dir else None
        if folder and not folder.is_dir():
            self.warnings.append(f"B-roll folder {local_dir} doesn't exist. Create it and add clips.")
        elif folder:
            self.local = [p for p in folder.rglob("*")
                          if p.suffix.lower() in VIDEO_EXT and not p.name.startswith(".")]
            if not self.local:
                self.warnings.append(f"B-roll folder {local_dir} has no .mp4/.mov clips in it.")

    def fill(self, m: dict) -> bool:
        hit = _local_match(m, self.local, self.used)
        if hit:
            m.update(source="local", file=str(hit))
            self.used.add(str(hit))
            return True
        if not self.key:
            self.misses.append(m.get("said") or m["search"])
            return False
        try:
            choice = _pexels_search(m["search"], m["seconds"], self.key, self.used)
        except RuntimeError as e:
            self.warnings.append(f"Pexels search for '{m['search']}' failed: {e}")
            return False
        if not choice:
            self.warnings.append(f"No Pexels clip found for '{m['search']}'.")
            return False
        m.update(choice)
        self.used.add(choice["pexels_id"])
        return True

    def report(self) -> list[str]:
        out = list(self.warnings)
        if self.misses:
            said = [" ".join(norm(t) for t in x.split()) for x in dict.fromkeys(self.misses)]
            example = "-".join(_stem(t) for t in said[0].split())
            out.append(f"No clip in {self.label or 'your B-roll folder'} for: {', '.join(said)}. "
                       f"Add clips named after what's in them, e.g. {example}-1.mp4 "
                       f"(no Pexels key, so there's no stock fallback).")
        return list(dict.fromkeys(out))


# Filename words that say nothing about what's in the clip.
_NOISE = {"img", "mov", "mp4", "clip", "video", "broll", "roll", "the", "a", "and", "of", "my",
          "final", "edit", "copy", "new", "vid", "pxl", "dji", "gopro", "trim"}
# Search words too generic to pick a clip by themselves.
_GENERIC = {"house", "home", "yard", "winter", "summer", "spring", "autumn", "fall", "new", "england"}


def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ves"):
        return w[:-3] + "f"          # leaves -> leaf
    for suf in ("ing", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]    # gutters -> gutter, plowing -> plow
    return w


def _terms(text: str) -> set[str]:
    toks = (norm(t) for t in re.split(r"[^A-Za-z0-9]+", text))
    return {_stem(t) for t in toks if t and not t.isdigit() and t not in _NOISE}


def _local_match(m: dict, files: list[Path], used: set) -> Path | None:
    """Picks your clip whose file name (or subfolder name) matches what you said.

    "gutter.mp4", "Gutters 2.mov" and "gutters/IMG_4821.MOV" all match when you
    say "gutters". The topic's other keywords and its search words count too, but
    a lone generic word like "house" is not enough to call it a match.
    """
    say = _terms(" ".join(m.get("keywords", [])) + " " + m.get("said", ""))
    search = _terms(m["search"])
    specific, generic = search - _GENERIC - say, search & _GENERIC
    best, best_score = None, 0.0
    for f in files:
        if str(f) in used:
            continue
        name = _terms(f.stem) | _terms(f.parent.name)
        score = 3 * len(say & name) + len(specific & name) + 0.4 * len(generic & name)
        if score >= 1 and score > best_score:
            best, best_score = f, score
    return best


def _pexels_search(query: str, seconds: float, key: str, used: set) -> dict | None:
    for orientation in ("portrait", None):
        params = {"query": query, "per_page": 20, "size": "medium"}
        if orientation:
            params["orientation"] = orientation
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(params)
        data = _get_json(url, key)
        for v in data.get("videos", []):
            if v["id"] in used or v.get("duration", 0) < seconds + 1:
                continue
            f = _best_file(v.get("video_files", []))
            if f:
                return {"source": "pexels", "pexels_id": v["id"], "download": f["link"],
                        "page": v.get("url", ""), "by": (v.get("user") or {}).get("name", ""),
                        "clip_length": v.get("duration", 0)}
    return None


def _best_file(files: list[dict]) -> dict | None:
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")]
    if not mp4:
        return None
    # Prefer vertical, then the size closest to 1080 wide without going huge.
    return min(mp4, key=lambda f: (f["height"] < f["width"], abs(min(f["width"], f["height"]) - 1080)))


def _get_json(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        hint = " (check PEXELS_API_KEY)" if e.code in (401, 403) else ""
        raise RuntimeError(f"HTTP {e.code}{hint}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(str(e.reason)) from None


def local_path(m: dict) -> Path:
    """Downloads a Pexels clip into the cache (once) and returns its path."""
    if m.get("source") == "local" or m.get("file"):
        return Path(m["file"]).expanduser()
    dest = cache_dir() / "broll" / f"pexels-{m['pexels_id']}.mp4"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading B-roll: {m['search']} (Pexels {m['pexels_id']})")
        req = urllib.request.Request(m["download"], headers={"User-Agent": UA})
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    return dest
