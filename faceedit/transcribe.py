"""Word-level transcript with local Whisper (faster-whisper). Free, no key.

The first run downloads the model (~250-500 MB) once; after that it's offline.
"""
from __future__ import annotations

import json
from pathlib import Path

# Priming Whisper with fillers makes it keep "um"/"uh" instead of silently dropping
# them, so they can be cut.
PROMPT = "Umm, let me think like, hmm... Okay, uh, here's what I'm, like, thinking. My House Guardian."


def transcribe(path: str | Path, model: str = "small.en", language: str = "en") -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("faster-whisper isn't installed: pip install -r faceedit/requirements.txt")
    print(f"Transcribing with Whisper {model} (first run downloads the model)...")
    m = WhisperModel(model, device="auto", compute_type="int8")
    segments, _ = m.transcribe(
        str(path), language=language, word_timestamps=True,
        initial_prompt=PROMPT, condition_on_previous_text=False, vad_filter=False,
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": text, "s": round(w.start, 3), "e": round(w.end, 3)})
    return words


def load_words(path: str | Path) -> list[dict]:
    """Loads a transcript saved earlier: a list of {"w","s","e"} or a plan file."""
    data = json.loads(Path(path).read_text())
    words = data["words"] if isinstance(data, dict) else data
    return [{"w": w["w"], "s": float(w["s"]), "e": float(w["e"])} for w in words]
