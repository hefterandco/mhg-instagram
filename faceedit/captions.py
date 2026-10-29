"""Word-by-word burned-in captions as an ASS subtitle file (rendered by ffmpeg/libass)."""
from __future__ import annotations

import re


def _ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _clean(word: str) -> str:
    w = re.sub(r"[.,;:\"“”]+", "", word).strip()
    return w.replace("\\", "").replace("{", "(").replace("}", ")")


def chunk(words: list[dict], max_words: int, max_chars: int) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        text = _clean(w["w"])
        if not text:
            continue
        item = {**w, "t": text}
        too_long = cur and (len(cur) >= max_words or len(" ".join(c["t"] for c in cur + [item])) > max_chars)
        paused = cur and w["s"] - cur[-1]["e"] > 0.5
        if too_long or paused:
            chunks.append(cur)
            cur = []
        cur.append(item)
        if re.search(r"[.?!,;:]$", w["w"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: list[dict], cfg: dict, width: int, height: int) -> str:
    base, active = _ass_color(cfg["color"]), _ass_color(cfg["active_color"])
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cfg['font']},{cfg['size']},{base},{base},{_ass_color(cfg['outline_color'])},&H80000000,0,0,0,0,100,100,0,0,1,{cfg['outline']},3,2,90,90,{cfg['bottom_margin']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    # The spoken word is clay and slightly bigger; each new line pops in.
    big = cfg.get("active_scale", 100)
    on, off = f"{{\\c{active}\\fscx{big}\\fscy{big}}}", f"{{\\c{base}\\fscx100\\fscy100}}"
    grow = "\\t(0,90,\\fscx{0}\\fscy{0})"
    pop_on = f"{{\\c{active}\\fscx{big * .82:.0f}\\fscy{big * .82:.0f}{grow.format(big)}}}"
    pop_off = f"{{\\c{base}\\fscx82\\fscy82{grow.format(100)}}}"
    pop = "{\\fscx82\\fscy82" + grow.format(100) + "}"
    groups = chunk(words, cfg["max_words"], cfg["max_chars"])
    for gi, g in enumerate(groups):
        nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else None
        g_end = g[-1]["e"] + 0.25
        if nxt is not None:
            g_end = nxt if nxt - g[-1]["e"] < 0.6 else min(g_end, nxt)
        for wi, w in enumerate(g):
            start = w["s"] if wi else w["s"]
            end = g[wi + 1]["s"] if wi + 1 < len(g) else g_end
            if end <= start:
                continue
            popping = cfg.get("pop") and wi == 0
            a, b = (pop_on, pop_off) if popping else (on, off)
            text = " ".join((f"{a}{x['t']}{b}" if xi == wi else x["t"]) for xi, x in enumerate(g))
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{pop if popping else ''}{text}")
    return head + "\n".join(lines) + "\n"
