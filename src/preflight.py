from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.paths import (
    EXTRACTED_DIR,
    RAW_PDF_ROOT,
    preflight_json_path,
)
from src.subject_plan import (
    SUBJECT_PAPER_MARKS,
    load_subject_plan,
    load_variant_scope,
    variant_in_scope,
)
from src.utils import parse_caie_filename

_ARTIFACT_SPECS = {
    "pages": (
        "pages.csv",
        {"filename", "subject", "paper", "year", "session", "variant", "doc_type", "page", "text"},
    ),
    "qp_ms_pairs": (
        "qp_ms_pairs.csv",
        {"subject", "paper", "year", "session", "variant", "qp_filename", "ms_filename", "qp_text", "ms_text"},
    ),
    "questions": (
        "questions.csv",
        {"question_id", "subject", "paper", "year", "session", "variant", "question_number", "question_text", "subquestions", "total_marks"},
    ),
    "tagged_questions": (
        "tagged_questions.csv",
        {
            "question_id",
            "subject",
            "paper",
            "year",
            "session",
            "variant",
            "question_number",
            "question_text",
            "subquestions",
            "topic",
            "subtopic",
            "command_word",
            "difficulty",
            "subquestion_tags",
            "mark_scheme_points",
        },
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def _scope_subjects(
    requested_subjects: list[str] | None,
    configured_subjects: dict[str, list[str]],
) -> list[str]:
    if requested_subjects:
        return sorted({str(subject).strip() for subject in requested_subjects if str(subject).strip()})
    return sorted(configured_subjects)


def _new_coverage(subjects: list[str], subject_plan: dict[str, list[str]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        subject: {
            paper: {"qp_keys": set(), "ms_keys": set()}
            for paper in subject_plan.get(subject, [])
        }
        for subject in subjects
    }


def _key(metadata: dict[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(metadata["subject"]),
        str(metadata["paper"]),
        int(metadata["year"]),
        str(metadata["session"]),
        str(metadata["variant"]),
    )


def _coverage_report(
    coverage: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    report: dict[str, dict[str, dict[str, Any]]] = {}
    for subject, papers in coverage.items():
        report[subject] = {}
        for paper, values in papers.items():
            qp_keys = values["qp_keys"]
            ms_keys = values["ms_keys"]
            matched = qp_keys & ms_keys
            unmatched_qp = qp_keys - ms_keys
            unmatched_ms = ms_keys - qp_keys
            report[subject][paper] = {
                "qp_documents": len(qp_keys),
                "ms_documents": len(ms_keys),
                "matched_pairs": len(matched),
                "unmatched_qp_keys": [_key_label(key) for key in sorted(unmatched_qp)],
                "unmatched_ms_keys": [_key_label(key) for key in sorted(unmatched_ms)],
                "status": "ready" if qp_keys and qp_keys == ms_keys else "blocked",
            }
    return report


def _key_label(key: tuple[str, str, int, str, str]) -> str:
    return "::".join(str(value) for value in key)


def _artifact_info(
    path: Path,
    required_columns: set[str],
    subject: str,
    subject_plan: dict[str, list[str]],
    allowed_variants: set[str],
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "rows": 0,
        "sha256": None,
        "missing_columns": [],
        "out_of_scope_rows": 0,
        "paper_rows": {paper: 0 for paper in subject_plan.get(subject, [])},
        "missing_papers": [],
        "errors": [],
    }
    if not path.exists():
        info["errors"].append("missing artifact")
        return info

    info["sha256"] = _sha256(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            info["missing_columns"] = sorted(required_columns - columns)
            for row in reader:
                info["rows"] += 1
                row_subject = str(row.get("subject", "")).strip()
                row_paper = str(row.get("paper", "")).strip().lower()
                row_variant = str(row.get("variant", "")).strip()
                if (
                    row_subject != subject
                    or row_paper not in set(subject_plan.get(subject, []))
                    or not variant_in_scope(row_variant, allowed_variants)
                ):
                    info["out_of_scope_rows"] += 1
                else:
                    info["paper_rows"][row_paper] += 1
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        info["errors"].append(str(exc))

    info["missing_papers"] = sorted(
        paper for paper, row_count in info["paper_rows"].items() if row_count == 0
    )
    if info["missing_columns"]:
        info["errors"].append("missing required columns")
    if info["missing_papers"] and path.exists():
        info["errors"].append(
            "missing configured paper rows: " + ", ".join(info["missing_papers"])
        )
    return info


def build_preflight_report(
    requested_subjects: list[str] | None = None,
    *,
    raw_pdf_root: Path = RAW_PDF_ROOT,
    extracted_dir: Path = EXTRACTED_DIR,
    subject_plan: dict[str, list[str]] | None = None,
    allowed_variants: set[str] | None = None,
) -> dict[str, Any]:
    subject_plan = subject_plan or load_subject_plan()
    allowed_variants = allowed_variants if allowed_variants is not None else load_variant_scope()
    subjects = _scope_subjects(requested_subjects, subject_plan)
    unknown_subjects = sorted(set(subjects) - set(subject_plan))
    coverage = _new_coverage(subjects, subject_plan)
    valid_raw_files: list[dict[str, Any]] = []
    out_of_scope_raw_files: list[str] = []
    invalid_raw_files: list[str] = []

    raw_paths = sorted(raw_pdf_root.rglob("*.pdf")) if raw_pdf_root.exists() else []
    for path in raw_paths:
        metadata = parse_caie_filename(path.name)
        if metadata is None:
            invalid_raw_files.append(str(path))
            continue
        subject = str(metadata["subject"])
        paper = str(metadata["paper"])
        if (
            subject not in subjects
            or paper not in set(subject_plan.get(subject, []))
            or not variant_in_scope(metadata["variant"], allowed_variants)
        ):
            out_of_scope_raw_files.append(str(path))
            continue

        valid_raw_files.append({"path": str(path), **metadata, "sha256": _sha256(path)})
        bucket = coverage[subject][paper]
        key = _key(metadata)
        bucket[f"{metadata['doc_type']}_keys"].add(key)

    artifact_paths = {
        subject: {
            name: extracted_dir / f"{subject}_{suffix}"
            for name, (suffix, _) in _ARTIFACT_SPECS.items()
        }
        for subject in subjects
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for subject, paths in artifact_paths.items():
        artifacts[subject] = {}
        for name, path in paths.items():
            _, required_columns = _ARTIFACT_SPECS[name]
            artifacts[subject][name] = _artifact_info(
                path,
                required_columns,
                subject,
                subject_plan,
                allowed_variants,
            )

    coverage_report = _coverage_report(coverage)
    coverage_failures: list[str] = []
    for subject, papers in coverage_report.items():
        for paper, values in papers.items():
            if values["status"] == "ready":
                continue
            if values["matched_pairs"] == 0:
                coverage_failures.append(f"{subject}/{paper} has no matched QP/MS pair")
            if values["unmatched_qp_keys"]:
                coverage_failures.append(
                    f"{subject}/{paper} has unmatched QP keys: "
                    + ", ".join(values["unmatched_qp_keys"])
                )
            if values["unmatched_ms_keys"]:
                coverage_failures.append(
                    f"{subject}/{paper} has unmatched MS keys: "
                    + ", ".join(values["unmatched_ms_keys"])
                )
    artifact_failures = [
        f"{subject}/{name}: {error}"
        for subject, subject_artifacts in artifacts.items()
        for name, info in subject_artifacts.items()
        for error in info["errors"]
    ]
    artifact_failures.extend(
        f"{subject}/{name}: {info['out_of_scope_rows']} out-of-scope rows"
        for subject, subject_artifacts in artifacts.items()
        for name, info in subject_artifacts.items()
        if info["out_of_scope_rows"]
    )
    failure_reasons = []
    if unknown_subjects:
        failure_reasons.append(f"unknown subjects requested: {', '.join(unknown_subjects)}")
    if invalid_raw_files:
        failure_reasons.append(f"invalid raw PDF filenames: {len(invalid_raw_files)}")
    if not valid_raw_files:
        failure_reasons.append("no in-scope raw PDFs found")
    failure_reasons.extend(coverage_failures)
    failure_reasons.extend(artifact_failures)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": {"commit": _git_value("rev-parse", "HEAD"), "branch": _git_value("branch", "--show-current")},
        "scope": {
            "subjects": subjects,
            "papers": {subject: subject_plan.get(subject, []) for subject in subjects},
            "allowed_variants": sorted(allowed_variants),
            "paper_marks": {
                subject: {
                    paper: SUBJECT_PAPER_MARKS.get(subject, {}).get(paper)
                    for paper in subject_plan.get(subject, [])
                }
                for subject in subjects
            },
        },
        "raw_pdfs": {
            "root": str(raw_pdf_root),
            "valid_in_scope": valid_raw_files,
            "out_of_scope": out_of_scope_raw_files,
            "invalid_filenames": invalid_raw_files,
        },
        "coverage": coverage_report,
        "artifacts": artifacts,
        "status": "ready" if not failure_reasons else "blocked",
        "failure_reasons": failure_reasons,
    }


def write_preflight_report(report: dict[str, Any], output_path: Path | None = None) -> Path:
    output_path = output_path or preflight_json_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def run_preflight(
    requested_subjects: list[str] | None = None,
    *,
    output_path: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    report = build_preflight_report(requested_subjects)
    report_path = write_preflight_report(report, output_path)
    print(f"Preflight status: {report['status']}")
    print(f"Preflight report: {report_path}")
    for reason in report["failure_reasons"]:
        print(f"- {reason}")
    return report, report_path
