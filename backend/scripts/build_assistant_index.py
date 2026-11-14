"""Rebuild the assistant's offline search index from data/docs (files + docs.json)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import assistant  # noqa: E402

if __name__ == "__main__":
    print(assistant.build_index())
