"""Save today's data/ideas.json as data/ideas_history/<date>.json.

Run after the morning research job updates data/ideas.json, and commit the new
file with it. The Journal tab uses this history to check how each idea did.

    python tools/archive_ideas.py
"""
import json
import shutil
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    src = DATA / "ideas.json"
    try:
        date = json.loads(src.read_text())["date"]
    except (OSError, ValueError, KeyError) as e:
        print(f"Can't read the date from {src}: {e}", file=sys.stderr)
        return 1
    dest = DATA / "ideas_history" / f"{date}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    print(f"Saved {dest.relative_to(DATA.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
