#!/usr/bin/env python3
"""Restore sanitized committed history as the next CI run's comparison base."""
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public-data" / "history"
TARGET = ROOT / "data" / "history"


def main():
    if not SOURCE.exists():
        print("public history: none yet")
        return
    TARGET.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in SOURCE.glob("*.json"):
        shutil.copy2(path, TARGET / path.name)
        copied += 1
    print(f"public history: restored {copied} files")


if __name__ == "__main__":
    main()
