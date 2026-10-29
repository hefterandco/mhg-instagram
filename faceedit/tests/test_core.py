"""Quick checks for the editing logic. Run: python -m pytest faceedit/tests  (or python faceedit/tests/test_core.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faceedit import broll, cuts  # noqa: E402
from faceedit.captions import build_ass, chunk  # noqa: E402
from faceedit.config import load_settings  # noqa: E402

S = load_settings()


def words(*spec):
    return [{"w": w, "s": s, "e": e} for w, s, e in spec]


def test_fillers_and_pauses_are_cut():
    ws = words(("Hi", 0.5, 0.8), ("um,", 1.0, 1.3), ("gutters", 3.0, 3.5), ("now.", 3.6, 3.9))
    cuts.mark_fillers(ws, S["cuts"]["fillers"])
    assert [w["filler"] for w in ws] == [False, True, False, False]
    segs = cuts.keep_segments(ws, 5.0, 0.3, 0.08, 0.14)
    assert len(segs) == 2 and segs[0]["end"] < 1.0 and segs[1]["start"] > 2.8


def test_time_mapping():
    segs = [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 5.0}]
    assert cuts.to_edited(1.5, segs) == 0.5
    assert cuts.to_edited(4.5, segs) == 1.5
    assert cuts.to_edited(3.0, segs) is None


def test_company_name_correction():
    ws = words(("My", 0, .1), ("home", .1, .2), ("guardian.", .2, .3))
    cuts.apply_corrections(ws, S["captions"]["corrections"])
    assert " ".join(w["w"] for w in ws) == "My House Guardian."


def test_caption_chunks_and_ass():
    ws = words(("Your", 0, .2), ("gutters", .25, .5), ("are", .55, .7), ("full.", .75, 1.0), ("Call", 2.0, 2.3))
    groups = chunk(ws, 3, 18)
    assert [len(g) for g in groups] == [3, 1, 1]
    ass = build_ass(ws, S["captions"], 1080, 1920)
    assert ass.count("Dialogue:") == 5 and "full." not in ass  # periods stripped


def test_broll_picks_specific_topic_and_respects_hook():
    ws = words(*[(f"w{i}", i * 0.5, i * 0.5 + 0.3) for i in range(40)])
    ws[2]["w"] = "gutters"      # inside the protected hook: skipped
    ws[20]["w"] = "house"       # generic
    ws[22]["w"] = "basement"    # specific: wins
    segs = [{"start": 0.0, "end": 20.0}]
    topics = broll.load_topics()
    import tempfile
    finder_dir = Path(tempfile.mkdtemp())
    (finder_dir / "basement-sump-pump.mp4").write_bytes(b"")
    (finder_dir / "colonial-house.mp4").write_bytes(b"")
    picked, _ = broll.choose(ws, segs, topics, S["broll"], str(finder_dir))
    assert picked and picked[0]["said"] == "basement"
    assert all(p["at"] > S["broll"]["protect_start"] for p in picked)


def test_retake_drops_earlier_take():
    ws = words(("My", 1, 1.2), ("House", 1.2, 1.4), ("Guardian", 1.4, 1.7), ("gives", 1.7, 1.9), ("you", 1.9, 2.0),
               ("or", 2.0, 2.1), ("family", 2.1, 2.5), ("help.", 2.5, 2.9),
               ("My", 3.8, 4.0), ("House", 4.0, 4.2), ("Guardian", 4.2, 4.5), ("gives", 4.5, 4.7), ("your", 4.7, 4.9),
               ("family", 4.9, 5.3), ("help.", 5.3, 5.7))
    dropped = cuts.mark_retakes(ws)
    assert len(dropped) == 1 and dropped[0].startswith("My House Guardian gives you")
    assert all(w.get("retake") for w in ws[:8]) and not any(w.get("retake") for w in ws[8:])
    segs = cuts.keep_segments(ws, 6.0, 0.3, 0.12, 0.22)
    assert segs[0]["start"] > 3.5  # the first take is gone


def test_same_line_said_far_apart_is_not_a_retake():
    line = [("That's", 0, .2), ("why", .2, .4), ("I'm", .4, .6), ("building", .6, .9), ("this.", .9, 1.2)]
    ws = words(*line, *[(w, s + 30, e + 30) for w, s, e in line])
    assert cuts.mark_retakes(ws) == []


def test_remove_spans_splits_segments():
    segs = cuts.remove_spans([{"start": 0.0, "end": 5.0}], [(1.0, 1.4), (4.95, 6.0)])
    assert segs == [{"start": 0.0, "end": 1.0}, {"start": 1.4, "end": 4.95}]


def test_hyphenated_words_are_rejoined_in_captions():
    ws = words(("one", 0, .2), ("-call", .2, .4), ("handle", .5, .7), ("-it", .7, .8), ("-all.", .8, 1.0))
    assert [[w["t"] for w in g] for g in chunk(ws, 3, 30)] == [["one-call", "handle-it-all"]]


def test_broll_ignores_company_name_and_matches_hyphenated_phrases():
    import tempfile
    ws = words(*[(f"w{i}", i * 0.5, i * 0.5 + 0.3) for i in range(60)])
    for k, t in zip(range(8, 11), ("My", "House", "Guardian")):
        ws[k]["w"] = t                       # company name: must not trigger "house" B-roll
    ws[30]["w"], ws[31]["w"], ws[32]["w"] = "long", "to", "-do"
    ws[33]["w"] = "list."
    segs = [{"start": 0.0, "end": 30.0}]
    d = Path(tempfile.mkdtemp())
    (d / "colonial-house.mp4").write_bytes(b"")
    (d / "home-to-do-list-checklist.mp4").write_bytes(b"")
    picked, _ = broll.choose(ws, segs, broll.load_topics(), S["broll"], str(d))
    assert [p["said"] for p in picked] == ["to-do list."]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
