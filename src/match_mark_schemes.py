from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.paths import pages_csv_path, qp_ms_pairs_csv_path
from src.utils import parse_caie_filename

logger = logging.getLogger(__name__)

_MATCH_KEY_COLUMNS = ("subject", "paper", "year", "session", "variant")
_REQUIRED_COLUMNS = {
    "filename",
    "subject",
    "paper",
    "year",
    "session",
    "variant",
    "doc_type",
    "page",
    "text",
}
_OUTPUT_COLUMNS = [
    "subject",
    "paper",
    "year",
    "session",
    "variant",
    "qp_filename",
    "ms_filename",
    "qp_text",
    "ms_text",
]

MatchKey = tuple[str, str, int, str, str]


def _key_from_metadata(metadata: dict[str, object]) -> MatchKey:
    return (
        str(metadata["subject"]),
        str(metadata["paper"]),
        int(metadata["year"]),
        str(metadata["session"]),
        str(metadata["variant"]),
    )


def _full_text(file_pages: pd.DataFrame) -> str:
    ordered_pages = file_pages.sort_values("page", kind="stable")
    page_texts = [
        "" if pd.isna(text_value) else str(text_value)
        for text_value in ordered_pages["text"]
    ]
    return "\n".join(page_texts).strip()


def _collect_file_records(
    pages: pd.DataFrame,
    subject: str,
    doc_type: str,
) -> dict[MatchKey, dict[str, str]]:
    records: dict[MatchKey, dict[str, str]] = {}
    subject_pages = pages[pages["subject"].astype(str).str.strip() == str(subject)]
    typed_pages = subject_pages[subject_pages["doc_type"].astype(str).str.lower() == doc_type]

    for filename_value, file_pages in typed_pages.groupby("filename", dropna=False):
        if pd.isna(filename_value):
            logger.warning("Skipping %s pages with no filename for subject %s.", doc_type, subject)
            continue

        filename = str(filename_value)
        metadata = parse_caie_filename(filename)
        if metadata is None:
            logger.warning("Skipping %s file with invalid CAIE filename: %s", doc_type, filename)
            continue
        if metadata["doc_type"] != doc_type:
            logger.warning(
                "Skipping %s file whose filename doc_type disagrees with the CSV: %s",
                doc_type,
                filename,
            )
            continue

        key = _key_from_metadata(metadata)
        record = {"filename": filename, "text": _full_text(file_pages)}
        if key in records:
            logger.warning(
                "Multiple %s files share match key %s; combining their page text: %s and %s",
                doc_type,
                key,
                records[key]["filename"],
                filename,
            )
            records[key]["filename"] = f"{records[key]['filename']};{filename}"
            records[key]["text"] = f"{records[key]['text']}\n{record['text']}".strip()
        else:
            records[key] = record

    return records


def _format_match_key(key: MatchKey) -> str:
    return ", ".join(f"{column}={value}" for column, value in zip(_MATCH_KEY_COLUMNS, key))


def match_mark_schemes(
    subject: str,
    pages_csv: Path | None = None,
    output_csv: Path | None = None,
) -> pd.DataFrame:
    """Pair complete QP and MS page text using shared filename metadata."""

    pages_csv = pages_csv or pages_csv_path(subject)
    output_csv = output_csv or qp_ms_pairs_csv_path(subject)

    if not pages_csv.exists():
        raise FileNotFoundError(f"Missing pages CSV: {pages_csv}. Run extraction first.")

    pages = pd.read_csv(pages_csv)
    missing = _REQUIRED_COLUMNS.difference(set(pages.columns))
    if missing:
        missing_csv = ", ".join(sorted(missing))
        raise ValueError(f"Pages CSV missing required columns: {missing_csv}")

    qp_records = _collect_file_records(pages, subject, "qp")
    ms_records = _collect_file_records(pages, subject, "ms")

    for key in sorted(qp_records.keys() - ms_records.keys()):
        logger.warning(
            "No matching mark scheme for question paper %s (%s).",
            qp_records[key]["filename"],
            _format_match_key(key),
        )
    for key in sorted(ms_records.keys() - qp_records.keys()):
        logger.warning(
            "No matching question paper for mark scheme %s (%s).",
            ms_records[key]["filename"],
            _format_match_key(key),
        )

    pair_rows: list[dict[str, object]] = []
    for key in sorted(qp_records.keys() & ms_records.keys()):
        subject_value, paper, year, session, variant = key
        pair_rows.append(
            {
                "subject": subject_value,
                "paper": paper,
                "year": year,
                "session": session,
                "variant": variant,
                "qp_filename": qp_records[key]["filename"],
                "ms_filename": ms_records[key]["filename"],
                "qp_text": qp_records[key]["text"],
                "ms_text": ms_records[key]["text"],
            }
        )

    pairs = pd.DataFrame(pair_rows, columns=_OUTPUT_COLUMNS)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Matched {len(pairs)} QP/MS pairs into {output_csv}")
    return pairs


if __name__ == "__main__":
    print("Use `python -m src.cli match --subject <code>` to match question papers and mark schemes.")
