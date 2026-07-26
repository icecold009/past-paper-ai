from __future__ import annotations

import argparse

from src.analyze_questions import analyze_questions
from src.build_prompt import build_prompt
from src.extract_pdfs import extract_all_pdfs
from src.generate_paper import generate_practice_paper
from src.match_mark_schemes import match_mark_schemes
from src.paths import RAW_PDF_ROOT, generated_prompt_md_path
from src.segment_questions import segment_questions
from src.subject_plan import load_subject_plan
from src.utils import parse_caie_filename


def discover_subjects() -> list[str]:
    if not RAW_PDF_ROOT.exists():
        return []

    subjects: set[str] = set()
    for pdf_path in RAW_PDF_ROOT.rglob("*.pdf"):
        metadata = parse_caie_filename(pdf_path.name)
        if metadata is not None:
            subjects.add(str(metadata["subject"]))

    return sorted(subjects)


def resolve_subjects(requested_subjects: list[str] | None) -> list[str]:
    if requested_subjects:
        return sorted({s.strip() for s in requested_subjects if s.strip()})
    plan = load_subject_plan()
    if plan:
        return sorted(plan.keys())
    return discover_subjects()


def validate_raw_pdfs(subjects: list[str] | None = None) -> int:
    total_pdfs = 0
    invalid_files: list[str] = []
    plan = load_subject_plan()
    selected_subjects = set(resolve_subjects(subjects)) if subjects else None

    if not RAW_PDF_ROOT.exists():
        print(f"Missing directory: {RAW_PDF_ROOT}")
        print("No PDFs found yet. You can still proceed with --mock in later stages.")
        return 0

    for pdf_path in sorted(RAW_PDF_ROOT.rglob("*.pdf")):
        metadata = parse_caie_filename(pdf_path.name)
        if metadata is None:
            total_pdfs += 1
            invalid_files.append(str(pdf_path))
            continue

        if selected_subjects is not None and metadata["subject"] not in selected_subjects:
            continue

        if metadata["subject"] in plan and plan[metadata["subject"]]:
            if metadata["paper"] not in set(plan[metadata["subject"]]):
                continue

        total_pdfs += 1

    if subjects and total_pdfs == 0:
        print(f"No PDFs found for requested subjects: {', '.join(subjects)}")
        print("You can still proceed with --mock in later stages.")
        return 0

    if total_pdfs == 0:
        print("No PDFs found yet. You can still proceed with --mock in later stages.")

    if invalid_files:
        print("Invalid filenames found:")
        for path in invalid_files:
            print(f"- {path}")
        return 1

    if selected_subjects:
        print(
            "Validation complete. "
            f"PDFs found: {total_pdfs}. "
            f"Subjects: {', '.join(sorted(selected_subjects))}. "
            "Filename format is valid."
        )
    else:
        print(f"Validation complete. PDFs found: {total_pdfs}. Filename format is valid.")
    return 0


def run_pipeline(
    subject: str,
    use_mock_if_missing: bool = False,
    subject_papers: dict[str, list[str]] | None = None,
) -> int:
    extracted = extract_all_pdfs(subjects=[subject], subject_papers=subject_papers)
    extracted_rows = len(extracted.get(subject, []))
    if not use_mock_if_missing and extracted_rows == 0:
        print(
            f"No extracted pages for {subject}. "
            "Stopping run to avoid generating empty artifacts. "
            "Add PDFs first, or run with --mock if this is intentional."
        )
        return 1

    mock_papers = subject_papers.get(subject) if subject_papers else None
    segment_questions(subject=subject, use_mock_if_missing=use_mock_if_missing, mock_papers=mock_papers)
    analyze_questions(subject=subject, planned_papers=mock_papers)
    build_prompt(subject=subject)
    print(f"Pipeline completed for {subject}. Prompt ready at {generated_prompt_md_path(subject)}")
    return 0


def _add_subject_argument(command_parser: argparse.ArgumentParser) -> None:
    command_parser.add_argument(
        "--subject",
        action="append",
        help="Subject code to process (repeat for multiple), e.g. --subject 9618 --subject 9702",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Pipeline CLI for past-paper-ai",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate raw PDF folders and filename rules")
    _add_subject_argument(validate_parser)

    extract_parser = subparsers.add_parser("extract", help="Extract page-level text from PDFs")
    _add_subject_argument(extract_parser)
    extract_parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Return non-zero exit code if no pages are extracted",
    )

    segment_parser = subparsers.add_parser("segment", help="Segment page text into question rows")
    _add_subject_argument(segment_parser)
    segment_parser.add_argument(
        "--mock",
        action="store_true",
        help="Create and use mock pages CSV when extraction output is missing",
    )

    match_parser = subparsers.add_parser(
        "match", help="Pair question-paper and mark-scheme page text"
    )
    _add_subject_argument(match_parser)

    analyze_parser = subparsers.add_parser(
        "analyze", help="Create stats, representative samples, and blueprint scaffold"
    )
    _add_subject_argument(analyze_parser)

    prompt_parser = subparsers.add_parser(
        "build-prompt", help="Build generation prompt from blueprint and samples"
    )
    _add_subject_argument(prompt_parser)

    generate_parser = subparsers.add_parser("generate", help="Generate practice paper draft via Gemini")
    _add_subject_argument(generate_parser)
    generate_parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model name for generation",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Gemini call and write a local dry-run draft",
    )

    run_parser = subparsers.add_parser("run", help="Run extract -> segment -> analyze -> build-prompt")
    _add_subject_argument(run_parser)
    run_parser.add_argument(
        "--mock",
        action="store_true",
        help="Allow mock pages CSV in segmentation if extraction output is missing",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    subjects = resolve_subjects(args.subject)
    subject_plan = load_subject_plan()

    if args.command == "validate":
        return validate_raw_pdfs(subjects=args.subject)

    if not subjects:
        print("No subjects were discovered. Add PDFs or pass --subject to proceed.")
        return 1

    if args.command == "extract":
        extracted = extract_all_pdfs(subjects=subjects, subject_papers=subject_plan)
        if args.fail_on_empty:
            empty_subjects = [subject for subject, df in extracted.items() if df.empty]
            if empty_subjects:
                print(f"No pages extracted for subjects: {', '.join(empty_subjects)}")
                return 1
        return 0

    if args.command == "segment":
        for subject in subjects:
            mock_papers = subject_plan.get(subject)
            segment_questions(subject=subject, use_mock_if_missing=args.mock, mock_papers=mock_papers)
        return 0

    if args.command == "match":
        for subject in subjects:
            match_mark_schemes(subject=subject)
        return 0

    if args.command == "analyze":
        for subject in subjects:
            analyze_questions(subject=subject, planned_papers=subject_plan.get(subject))
        return 0

    if args.command == "build-prompt":
        for subject in subjects:
            build_prompt(subject=subject)
        return 0

    if args.command == "run":
        has_failure = False
        for subject in subjects:
            result = run_pipeline(
                subject=subject,
                use_mock_if_missing=args.mock,
                subject_papers=subject_plan,
            )
            if result != 0:
                has_failure = True
        return 1 if has_failure else 0

    if args.command == "generate":
        has_failure = False
        for subject in subjects:
            try:
                output_path = generate_practice_paper(
                    subject=subject,
                    model_name=args.model,
                    dry_run=args.dry_run,
                )
                print(f"Generated paper draft for {subject} at {output_path}")
            except Exception as exc:
                has_failure = True
                print(f"Generation failed for {subject}: {exc}")
        return 1 if has_failure else 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
