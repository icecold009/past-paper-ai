from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_PDF_ROOT = _PROJECT_ROOT / "data/raw_pdfs"

EXTRACTED_DIR = _PROJECT_ROOT / "data/extracted"

OUTPUTS_DIR = _PROJECT_ROOT / "outputs"

PROMPTS_DIR = _PROJECT_ROOT / "prompts"


def pages_csv_path(subject: str) -> Path:
    return EXTRACTED_DIR / f"{subject}_pages.csv"


def questions_csv_path(subject: str) -> Path:
    return EXTRACTED_DIR / f"{subject}_questions.csv"


def question_stats_csv_path(subject: str) -> Path:
    return OUTPUTS_DIR / f"{subject}_question_stats.csv"


def representative_questions_csv_path(subject: str) -> Path:
    return OUTPUTS_DIR / f"{subject}_representative_questions.csv"


def blueprint_json_path(subject: str) -> Path:
    return OUTPUTS_DIR / f"{subject}_blueprint_scaffold.json"


def generated_prompt_md_path(subject: str) -> Path:
    return PROMPTS_DIR / f"{subject}_practice_paper_prompt.md"


def generated_paper_md_path(subject: str) -> Path:
    return OUTPUTS_DIR / f"{subject}_practice_paper_draft.md"
