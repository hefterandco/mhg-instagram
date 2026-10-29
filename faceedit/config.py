"""Settings: faceedit.toml for look and behavior, environment / .env for keys."""
from __future__ import annotations

import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
ASSETS = PKG / "assets"
FONTS = ASSETS / "fonts"


def load_dotenv() -> None:
    """Reads KEY=value lines from the repo's .env (local testing only; never committed)."""
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value and not set(value) <= {"_"}:  # skip unfilled ____ blanks
            os.environ.setdefault(key.strip(), value)


def load_settings(path: str | Path | None = None) -> dict:
    import tomllib  # Python 3.11+, needed only for editing
    with open(path or PKG / "faceedit.toml", "rb") as f:
        return tomllib.load(f)


def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return "" if set(value) <= {"_"} else value


def cache_dir() -> Path:
    d = Path(os.environ.get("FACEEDIT_CACHE") or Path.home() / ".cache" / "mhg-faceedit")
    d.mkdir(parents=True, exist_ok=True)
    return d
