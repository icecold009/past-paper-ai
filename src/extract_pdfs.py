from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

from src.utils import parse_9618_filename
from src.paths import PAGES_CSV, RAW_PDF_DIRS


OUTPUT_CSV = PAGES_CSV


def extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
    metadata = parse_9618_filename(pdf_path.name)
    if metadata is None:
        print(f"Warning: skipping file with unexpected name: {pdf_path}")
        return []

    rows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            rows.append(
                {
                    "filename": pdf_path.name,
                    "subject": metadata["subject"],
                    "paper": metadata["paper"],
                    "year": metadata["year"],
                    "session": metadata["session"],
                    "variant": metadata["variant"],
                    "doc_type": metadata["doc_type"],
                    "page": page_number,
                    "text": page.extract_text() or "",
                }
            )
    return rows


def extract_all_pdfs(raw_pdf_dirs: tuple[Path, ...] = RAW_PDF_DIRS) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    files_processed = 0

    for raw_dir in raw_pdf_dirs:
        if not raw_dir.exists():
            print(f"Warning: directory not found, skipping: {raw_dir}")
            continue

        for pdf_path in sorted(raw_dir.glob("*.pdf")):
            file_rows = extract_pdf_pages(pdf_path)
            if not file_rows:
                continue
            rows.extend(file_rows)
            files_processed += 1

    dataframe = pd.DataFrame(
        rows,
        columns=[
            "filename",
            "subject",
            "paper",
            "year",
            "session",
            "variant",
            "doc_type",
            "page",
            "text",
        ],
    )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"Processed {files_processed} files and {len(dataframe)} rows into {OUTPUT_CSV}")
    return dataframe


if __name__ == "__main__":
    extract_all_pdfs()
