from __future__ import annotations

import argparse
from pathlib import Path

from src.analyze_questions import analyze_questions
from src.build_prompt import build_prompt
from src.extract_pdfs import extract_all_pdfs
from src.paths import GENERATED_PROMPT_MD, PAGES_CSV, QUESTIONS_CSV, RAW_PDF_DIRS
from src.segment_questions import segment_questions
from src.utils import parse_9618_filename


def validate_raw_pdfs(raw_pdf_dirs: tuple[Path, ...] = RAW_PDF_DIRS) -> int:
    total_pdfs = 0
    invalid_files: list[str] = []

    for raw_dir in raw_pdf_dirs:
        if not raw_dir.exists():
            print(f"Missing directory: {raw_dir}")
            continue

        for pdf_path in sorted(raw_dir.glob("*.pdf")):
            total_pdfs += 1
            if parse_9618_filename(pdf_path.name) is None:
                invalid_files.append(str(pdf_path))

    if total_pdfs == 0:
        print("No PDFs found yet. You can still proceed with --mock in later stages.")

    if invalid_files:
        print("Invalid filenames found:")
        for path in invalid_files:
            print(f"- {path}")
        return 1

    print(f"Validation complete. PDFs found: {total_pdfs}. Filename format is valid.")
    return 0


def run_pipeline(use_mock_if_missing: bool = False) -> int:
    extract_all_pdfs()
    segment_questions(use_mock_if_missing=use_mock_if_missing)
    analyze_questions()
    build_prompt()
    print(f"Pipeline completed. Prompt ready at {GENERATED_PROMPT_MD}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Pipeline CLI for past-paper-ai",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate raw PDF folders and filename rules")

    extract_parser = subparsers.add_parser("extract", help="Extract page-level text from PDFs")
    extract_parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Return non-zero exit code if no pages are extracted",
    )

    segment_parser = subparsers.add_parser("segment", help="Segment page text into question rows")
    segment_parser.add_argument(
        "--mock",
        action="store_true",
        help="Create and use mock pages CSV when extraction output is missing",
    )

    subparsers.add_parser("analyze", help="Create stats, representative samples, and blueprint scaffold")
    subparsers.add_parser("build-prompt", help="Build generation prompt from blueprint and samples")

    run_parser = subparsers.add_parser("run", help="Run extract -> segment -> analyze -> build-prompt")
    run_parser.add_argument(
        "--mock",
        action="store_true",
        help="Allow mock pages CSV in segmentation if extraction output is missing",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "validate":
        return validate_raw_pdfs()

    if args.command == "extract":
        pages = extract_all_pdfs()
        if args.fail_on_empty and pages.empty:
            print(f"No pages extracted into {PAGES_CSV}")
            return 1
        return 0

    if args.command == "segment":
        segment_questions(pages_csv=PAGES_CSV, output_csv=QUESTIONS_CSV, use_mock_if_missing=args.mock)
        return 0

    if args.command == "analyze":
        analyze_questions(questions_csv=QUESTIONS_CSV)
        return 0

    if args.command == "build-prompt":
        build_prompt()
        return 0

    if args.command == "run":
        return run_pipeline(use_mock_if_missing=args.mock)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
