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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
