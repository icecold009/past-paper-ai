from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

from src.paths import RAW_PDF_ROOT, pages_csv_path
from src.subject_plan import variant_in_scope
from src.utils import parse_caie_filename


def extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
    metadata = parse_caie_filename(pdf_path.name)
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


def extract_subject_pdfs(
    subject: str,
    raw_pdf_root: Path = RAW_PDF_ROOT,
    allowed_papers: set[str] | None = None,
    allowed_variants: set[str] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    files_processed = 0

    if not raw_pdf_root.exists():
        print(f"Warning: directory not found, skipping: {raw_pdf_root}")
        return pd.DataFrame(
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
            ]
        )

    for pdf_path in sorted(raw_pdf_root.rglob("*.pdf")):
        metadata = parse_caie_filename(pdf_path.name)
        if metadata is None or metadata["subject"] != subject:
            continue
        if allowed_papers is not None and metadata["paper"] not in allowed_papers:
            continue
        if not variant_in_scope(metadata["variant"], allowed_variants):
            continue

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

    output_csv = pages_csv_path(subject)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Processed {files_processed} files and {len(dataframe)} rows into {output_csv}")
    return dataframe


def extract_all_pdfs(
    subjects: list[str],
    raw_pdf_root: Path = RAW_PDF_ROOT,
    subject_papers: dict[str, list[str]] | None = None,
    allowed_variants: set[str] | None = None,
) -> dict[str, pd.DataFrame]:
    extracted: dict[str, pd.DataFrame] = {}
    for subject in subjects:
        allowed = None
        if subject_papers is not None and subject in subject_papers and subject_papers[subject]:
            allowed = set(subject_papers[subject])
        extracted[subject] = extract_subject_pdfs(
            subject=subject,
            raw_pdf_root=raw_pdf_root,
            allowed_papers=allowed,
            allowed_variants=allowed_variants,
        )
    return extracted


if __name__ == "__main__":
    print("Use `python -m src.cli extract --subject <code>` to run extraction.")
