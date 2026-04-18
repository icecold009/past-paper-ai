from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

from src.extract_pdfs import extract_all_pdfs


if __name__ == "__main__":
    print("Use `python -m src.cli extract --subject <code>` to run extraction.")