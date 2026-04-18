from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.paths import pages_csv_path, questions_csv_path

_QUESTION_START_RE = re.compile(r"(?m)^\s*(\d{1,2})[\.)]\s+")


def _split_questions(page_text: str) -> list[tuple[str, str]]:
    text = (page_text or "").strip()
    if not text:
        return []

    matches = list(_QUESTION_START_RE.finditer(text))
    if not matches:
        return [("", text)]

    chunks: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        question_number = match.group(1)
        question_text = text[start:end].strip()
        if question_text:
            chunks.append((question_number, question_text))

    return chunks


def _write_mock_pages_csv(subject: str, pages_csv: Path, mock_papers: list[str] | None = None) -> None:
    pages_csv.parent.mkdir(parents=True, exist_ok=True)
    papers = [p.strip().lower() for p in (mock_papers or ["p1", "p2"]) if p.strip()]
    if not papers:
        papers = ["p1"]

    first_paper = papers[0]
    second_paper = papers[1] if len(papers) > 1 else papers[0]

    mock_rows = [
        {
            "filename": f"{subject}_{first_paper}_2023_mj_11_qp.pdf",
            "subject": subject,
            "paper": first_paper,
            "year": 2023,
            "session": "May/June",
            "variant": "11",
            "doc_type": "qp",
            "page": 1,
            "text": "1. Explain two reasons why a CPU uses cache memory. [4]\n2. Describe one advantage of optical storage over magnetic storage. [2]",
        },
        {
            "filename": f"{subject}_{second_paper}_2023_mj_21_qp.pdf",
            "subject": subject,
            "paper": second_paper,
            "year": 2023,
            "session": "May/June",
            "variant": "21",
            "doc_type": "qp",
            "page": 1,
            "text": "1. Write pseudocode to validate a user input in the range 1 to 100. [5]\n2. State one use of an array in this program. [1]",
        },
    ]
    pd.DataFrame(mock_rows).to_csv(pages_csv, index=False, encoding="utf-8")


def segment_questions(
    subject: str,
    pages_csv: Path | None = None,
    output_csv: Path | None = None,
    use_mock_if_missing: bool = False,
    mock_papers: list[str] | None = None,
) -> pd.DataFrame:
    if pages_csv is None:
        pages_csv = pages_csv_path(subject)
    if output_csv is None:
        output_csv = questions_csv_path(subject)

    if not pages_csv.exists():
        if not use_mock_if_missing:
            raise FileNotFoundError(
                f"Missing pages CSV: {pages_csv}. Run extraction first or pass mock mode."
            )
        _write_mock_pages_csv(subject, pages_csv, mock_papers=mock_papers)

    pages = pd.read_csv(pages_csv)
    if use_mock_if_missing and pages.empty:
        _write_mock_pages_csv(subject, pages_csv, mock_papers=mock_papers)
        pages = pd.read_csv(pages_csv)
    required_columns = {"filename", "paper", "year", "session", "variant", "doc_type", "page", "text"}
    missing = required_columns.difference(set(pages.columns))
    if missing:
        missing_csv = ", ".join(sorted(missing))
        raise ValueError(f"Pages CSV missing required columns: {missing_csv}")

    question_rows: list[dict[str, object]] = []
    for row in pages.itertuples(index=False):
        if str(row.doc_type).lower() != "qp":
            continue

        chunks = _split_questions(str(row.text) if row.text is not None else "")
        for idx, (question_number, question_text) in enumerate(chunks, start=1):
            question_rows.append(
                {
                    "question_id": f"{row.filename}::p{row.page}::q{idx}",
                    "subject": subject,
                    "filename": row.filename,
                    "paper": row.paper,
                    "year": int(row.year),
                    "session": row.session,
                    "variant": row.variant,
                    "page": int(row.page),
                    "question_number": question_number,
                    "question_text": question_text,
                    "question_text_length": len(question_text),
                }
            )

    questions = pd.DataFrame(
        question_rows,
        columns=[
            "question_id",
            "subject",
            "filename",
            "paper",
            "year",
            "session",
            "variant",
            "page",
            "question_number",
            "question_text",
            "question_text_length",
        ],
    )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    questions.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Segmented {len(questions)} questions into {output_csv}")
    return questions


if __name__ == "__main__":
    print("Use `python -m src.cli segment --subject <code>` to run segmentation.")
