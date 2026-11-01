#!/usr/bin/env python3
"""Builds the Instagram results dashboard from insights/ into one self-contained HTML file.

  git pull && python tools/build_dashboard.py            # writes and prints the file path
  python tools/build_dashboard.py --out ~/Desktop/ig.html

The data is baked into the page, so it shows the numbers as of the last pull.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "dashboard.html"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "insights"), help="folder holding account/posts/stories.json")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "mhg-instagram-dashboard.html"))
    args = ap.parse_args()

    data_dir = Path(args.data)
    data = {}
    for name in ("account", "posts", "stories"):
        p = data_dir / f"{name}.json"
        data[name] = json.loads(p.read_text()) if p.exists() else {}
    # </ inside JSON would end the <script> block early.
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*DATA*/", blob, 1)
    out = Path(args.out).expanduser()
    out.write_text(html)
    print(out)


if __name__ == "__main__":
    main()
