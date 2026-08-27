from __future__ import annotations

from pathlib import Path

RAW_PDF_ROOT = Path("data/raw_pdfs")

EXTRACTED_DIR = Path("data/extracted")

OUTPUTS_DIR = Path("outputs")

PROMPTS_DIR = Path("prompts")


def pages_csv_path(subject: str) -> Path:
    return EXTRACTED_DIR / f"{subject}_pages.csv"


def questions_csv_path(subject: str) -> Path:
    return EXTRACTED_DIR / f"{subject}_questions.csv"


def qp_ms_pairs_csv_path(subject: str) -> Path:
    return EXTRACTED_DIR / f"{subject}_qp_ms_pairs.csv"


def tagged_questions_csv_path(subject: str) -> Path:
    return EXTRACTED_DIR / f"{subject}_tagged_questions.csv"


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


def preflight_json_path() -> Path:
    return OUTPUTS_DIR / "data_preflight.json"
