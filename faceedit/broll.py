"""Picks B-roll moments from what you say, and fetches matching clips.

Sources, in order: your own clips folder (if [broll] local_dir is set), then
Pixabay free stock video (PIXABAY_API_KEY), then Pexels (PEXELS_API_KEY); see
.env.example. Stock clips are downloaded once into the cache and reused.
"""
from __future__ import annotations

import hashlib
import json
import time
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

    finder = _Finder(local_dir, cfg)
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
        m = {"_t": at, "at": round(spoken[i]["s"] - 0.1, 3), "seconds": dur, "said": said,
             "kind": t.get("kind", ""), "search": t["search"], "stock": t.get("stock", []), "allow": t.get("allow", [])}
        if finder.fill(m):
            picked.append(m)
    picked.sort(key=lambda p: p["_t"])
    for p in picked:
        p.pop("_t")
    return picked, list(dict.fromkeys(finder.warnings))


def fill_missing(moments: list[dict], local_dir: str = "", cfg: dict | None = None) -> list[str]:
    """Finds clips for hand-added plan entries that only have a "search"."""
    finder = _Finder(local_dir, cfg or {})
    for m in moments:
        if not (m.get("file") or m.get("download")):
            finder.fill(m)
    return list(dict.fromkeys(finder.warnings))


# ---------------------------------------------------------------- sources

SOURCE_KEYS = ("source", "file", "download", "pixabay_id", "pexels_id", "page", "by", "tags", "query",
               "clip_length", "thumb")


def apply_option(m: dict, opt: dict) -> None:
    """Makes one candidate the clip this moment uses."""
    for k in SOURCE_KEYS:
        m.pop(k, None)
    m.update(opt)


class _Finder:
    def __init__(self, local_dir: str = "", cfg: dict | None = None):
        cfg = cfg or {}
        self.key = secret("PEXELS_API_KEY")
        self.pixabay = secret("PIXABAY_API_KEY")
        self.local = [p for p in Path(local_dir).expanduser().rglob("*")
                      if p.suffix.lower() in VIDEO_EXT] if local_dir else []
        self.n = cfg.get("options", 3)
        self.avoid = [a.lower() for a in cfg.get("avoid_tags", [])]
        self.used: set = set()
        self.warnings: list[str] = []

    def fill(self, m: dict) -> bool:
        """Finds up to `options` candidates: your own clips first, then stock (only for
        topics that allow it). The first is used; the rest go on the review sheet."""
        opts = [{"source": "local", "file": str(f)} for f in _local_matches(m["search"], self.local, self.used, self.n)]
        stock = m.get("stock") or []
        if len(opts) < self.n and stock and self.pixabay:
            try:
                opts += _pixabay_search(stock, m["seconds"], self.pixabay, self.used, self.n - len(opts),
                                        [a for a in self.avoid if a not in m.get("allow", [])])
            except RuntimeError as e:
                self.warnings.append(f"Pixabay search for '{m['search']}' failed: {e}")
        if len(opts) < self.n and stock and self.key:
            try:
                choice = _pexels_search(stock[0], m["seconds"], self.key, self.used)
                if choice:
                    opts.append(choice)
            except RuntimeError as e:
                self.warnings.append(f"Pexels search for '{m['search']}' failed: {e}")
        if not opts:
            why = (" Stock isn't used here: this moment should show your own service."
                   if not stock else " Nothing on-brand turned up in stock either.")
            self.warnings.append(f"No clip for \"{m['said']}\": film one and name it with \"{m['search']}\" "
                                 f"in ~/Movies/MHG-broll.{why}")
            return False
        for o in opts:
            self.used.add(o.get("file") or f"{o['source']}-{o.get(o['source'] + '_id')}")
        m["options"] = opts
        apply_option(m, opts[0])
        return True


def _local_matches(search: str, files: list[Path], used: set, n: int) -> list[Path]:
    words = set(search.lower().split())
    scored = []
    for f in files:
        if str(f) in used:
            continue
        name = set(norm(t) for t in f.stem.replace("_", " ").replace("-", " ").split())
        score = len(words & name)
        if score:
            scored.append((-score, f.name, f))
    return [f for _, _, f in sorted(scored)[:n]]


def _pixabay_search(queries: list[str], seconds: float, key: str, used: set, n: int = 1,
                    avoid: list[str] | None = None) -> list[dict]:
    """Up to n on-brand clips for the topic's short searches.

    Pixabay matches ANY word of a search ("air filter" returns sky clouds), so a
    clip only counts if its tags contain every word of the search, and none of
    the avoid tags (scare, security, off-region, brands...).
    """
    found = []
    for query in queries:
        params = {"key": key, "q": query[:100], "video_type": "film", "safesearch": "true", "per_page": 50}
        data = _cached_json("https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params))
        words = query.lower().split()
        hits = []
        for h in data.get("hits", []):
            tags = [t.strip() for t in h.get("tags", "").lower().split(",")]
            tag_words = {w for t in tags for w in t.split()}
            if (f"pixabay-{h['id']}" in used or any(f["pixabay_id"] == h["id"] for f in found)
                    or h.get("duration", 0) < seconds + 1
                    or not all(any(w in t for t in tags) for w in words)
                    or any(a in tags or (" " not in a and a in tag_words) for a in (avoid or []))):
                continue
            hits.append(h)
        # Vertical clips first (they fill a Reel without cropping), then Pixabay's own ranking.
        hits.sort(key=lambda h: h["videos"]["medium"]["height"] < h["videos"]["medium"]["width"])
        for h in hits:
            f = _pixabay_file(h["videos"])
            if f:
                found.append({"source": "pixabay", "pixabay_id": h["id"], "download": f["url"], "query": query,
                              "tags": h.get("tags", ""), "page": h.get("pageURL", ""), "by": h.get("user", ""),
                              "clip_length": h.get("duration", 0), "thumb": h["videos"]["medium"].get("thumbnail", "")})
                if len(found) >= n:
                    return found
    return found


def _pixabay_file(variants: dict) -> dict | None:
    """Sharp enough once cropped to 9:16 (short side >= 1080), without huge downloads."""
    ok = [variants[k] for k in ("medium", "large") if variants.get(k, {}).get("url")]
    good = [f for f in ok if min(f["width"], f["height"]) >= 1080 and f.get("size", 0) <= 80_000_000]
    return (good or ok or [None])[0]


def _cached_json(url: str) -> dict:
    """GET JSON, cached for 24 hours as Pixabay's API terms require."""
    path = cache_dir() / "pixabay" / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text())
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        hint = " (check PIXABAY_API_KEY)" if e.code in (400, 401, 403) else " (rate limit)" if e.code == 429 else ""
        raise RuntimeError(f"HTTP {e.code}{hint}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(str(e.reason)) from None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


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
    """Downloads a stock clip into the cache (once) and returns its path."""
    if m.get("source") == "local" or m.get("file"):
        return Path(m["file"]).expanduser()
    src = m.get("source", "pexels")
    clip_id = m.get(f"{src}_id")
    dest = cache_dir() / "broll" / f"{src}-{clip_id}.mp4"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading B-roll: {m['search']} ({src.title()} {clip_id})")
        req = urllib.request.Request(m["download"], headers={"User-Agent": UA})
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    return dest
