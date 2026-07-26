from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from src.paths import pages_csv_path, questions_csv_path

_QUESTION_START_RE = re.compile(
    r"^\s*(?P<number>\d{1,2})(?:\s*[\.)])?(?:\s*\([a-z]\))?(?:\s*\([ivxlcdm]+\))?\s+(?P<body>\S.*)$",
    re.IGNORECASE,
)
_MARK_RE = re.compile(r"\[(?P<marks>\d+)\]")
_SUBQUESTION_LABEL_RE = re.compile(
    r"(?P<label>(?:(?<![A-Za-z])\((?:[a-hj-z]|[ivxlcdm]+)\))+)",
    re.IGNORECASE,
)

_BOILERPLATE_PATTERNS = (
    re.compile(r"^\s*\d+\s*$"),
    re.compile(r"^\s*page\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*turn over\s*$", re.IGNORECASE),
    re.compile(r"^\s*please turn over\s*$", re.IGNORECASE),
    re.compile(r"^\s*continued on next page\s*$", re.IGNORECASE),
    re.compile(r"^\s*end of paper\s*$", re.IGNORECASE),
    re.compile(r"^\s*cambridge international\b", re.IGNORECASE),
    re.compile(r"^\s*do not write in this margin\b", re.IGNORECASE),
)


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _is_boilerplate_line(line: str) -> bool:
    if not line:
        return True

    for pattern in _BOILERPLATE_PATTERNS:
        if pattern.search(line):
            return True

    if not re.search(r"[A-Za-z]", line):
        return True

    return False


def _document_lines(pages: pd.DataFrame) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for page_number_value, page_text_value in pages.sort_values("page")[ ["page", "text"] ].itertuples(index=False, name=None):
        page_number = int(page_number_value)
        page_text = str(page_text_value) if page_text_value is not None else ""
        for raw_line in page_text.splitlines():
            line = _normalize_line(raw_line)
            if _is_boilerplate_line(line):
                continue
            lines.append((page_number, line))
    return lines


def _split_questions(document_lines: list[tuple[int, str]]) -> list[tuple[str, int, int, str]]:
    if not document_lines:
        return []

    chunks: list[tuple[str, int, int, str]] = []
    current_number: str | None = None
    current_start_page: int | None = None
    current_end_page: int | None = None
    current_lines: list[str] = []

    for page_number, line in document_lines:
        match = _QUESTION_START_RE.match(line)
        if match:
            if current_number is not None and current_start_page is not None and current_end_page is not None:
                question_text = "\n".join(current_lines).strip()
                if question_text:
                    chunks.append((current_number, current_start_page, current_end_page, question_text))

            current_number = match.group("number")
            current_start_page = page_number
            current_end_page = page_number
            current_lines = [line]
            continue

        if current_number is None:
            continue

        current_lines.append(line)
        current_end_page = page_number

    if current_number is not None and current_start_page is not None and current_end_page is not None:
        question_text = "\n".join(current_lines).strip()
        if question_text:
            chunks.append((current_number, current_start_page, current_end_page, question_text))

    return chunks


def _mark_total(text: str) -> int:
    return sum(int(match.group("marks")) for match in _MARK_RE.finditer(text))


def _clean_subquestion_text(text: str) -> str:
    without_marks = _MARK_RE.sub("", text)
    return re.sub(r"\s+", " ", without_marks).strip()


def parse_question_structure(question_text: str) -> tuple[list[dict[str, object]], int, int]:
    """Return labeled subquestions, unlabeled marks, and the total mark count.

    Subquestion labels are kept as they appear structurally in the source, so a
    nested label such as ``(a)(i)`` is represented as one explicit label. Marks
    before the first subquestion label belong to the top-level question; marks
    in each labeled segment belong to that subquestion.
    """

    label_matches = list(_SUBQUESTION_LABEL_RE.finditer(question_text))
    if not label_matches:
        marks = _mark_total(question_text)
        return [], marks, marks

    top_level_marks = _mark_total(question_text[: label_matches[0].start()])
    subquestions: list[dict[str, object]] = []
    for index, label_match in enumerate(label_matches):
        segment_end = (
            label_matches[index + 1].start()
            if index + 1 < len(label_matches)
            else len(question_text)
        )
        segment = question_text[label_match.end() : segment_end]
        subquestions.append(
            {
                "label": label_match.group("label").lower(),
                "text": _clean_subquestion_text(segment),
                "marks": _mark_total(segment),
            }
        )

    total_marks = top_level_marks + sum(int(item["marks"]) for item in subquestions)
    return subquestions, top_level_marks, total_marks


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
            "text": "1. Explain why a CPU uses cache memory. (a) State one reason. [2] (b) Explain another reason. [2]\n2. Describe one advantage of optical storage over magnetic storage. [2]",
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
            "text": "1. Write pseudocode to validate a user input in the range 1 to 100. (a)(i) State a validation condition. [2] (ii) Explain why it is needed. [3]\n2. State one use of an array in this program. [1]",
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
    document_columns = ["filename", "subject", "paper", "year", "session", "variant", "doc_type"]
    qp_pages = pages[pages["doc_type"].astype(str).str.lower() == "qp"]

    for document_key, document_pages in qp_pages.groupby(document_columns, dropna=False):
        filename, _, paper, _, _, _, _ = document_key
        lines = _document_lines(document_pages)
        chunks = _split_questions(lines)

        for idx, (question_number, start_page, end_page, question_text) in enumerate(chunks, start=1):
            page_label = str(start_page) if start_page == end_page else f"{start_page}-{end_page}"
            subquestions, top_level_marks, total_marks = parse_question_structure(question_text)
            question_rows.append(
                {
                    "question_id": f"{filename}::p{page_label}::q{idx}",
                    "subject": subject,
                    "filename": filename,
                    "paper": paper,
                    "year": int(document_pages.iloc[0].year),
                    "session": document_pages.iloc[0].session,
                    "variant": document_pages.iloc[0].variant,
                    "doc_type": "qp",
                    "page": int(start_page),
                    "page_end": int(end_page),
                    "question_number": question_number,
                    "question_text": question_text,
                    "question_text_length": len(question_text),
                    "marks": top_level_marks,
                    "subquestions": json.dumps(subquestions, ensure_ascii=False),
                    "total_marks": total_marks,
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
            "doc_type",
            "page",
            "page_end",
            "question_number",
            "question_text",
            "question_text_length",
            "marks",
            "subquestions",
            "total_marks",
        ],
    )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    questions.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Segmented {len(questions)} questions into {output_csv}")
    return questions


if __name__ == "__main__":
    print("Use `python -m src.cli segment --subject <code>` to run segmentation.")
