from __future__ import annotations

from pathlib import Path

RAW_PDF_DIRS = (
    Path("data/raw_pdfs/paper1/qp"),
    Path("data/raw_pdfs/paper1/ms"),
    Path("data/raw_pdfs/paper2/qp"),
    Path("data/raw_pdfs/paper2/ms"),
)

EXTRACTED_DIR = Path("data/extracted")
PAGES_CSV = EXTRACTED_DIR / "9618_pages.csv"
QUESTIONS_CSV = EXTRACTED_DIR / "9618_questions.csv"

OUTPUTS_DIR = Path("outputs")
QUESTION_STATS_CSV = OUTPUTS_DIR / "9618_question_stats.csv"
REPRESENTATIVE_QUESTIONS_CSV = OUTPUTS_DIR / "9618_representative_questions.csv"
BLUEPRINT_JSON = OUTPUTS_DIR / "9618_blueprint_scaffold.json"

PROMPTS_DIR = Path("prompts")
GENERATED_PROMPT_MD = PROMPTS_DIR / "practice_paper_prompt.md"
