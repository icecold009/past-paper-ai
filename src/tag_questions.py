from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from dotenv import load_dotenv

from src.paths import (
    qp_ms_pairs_csv_path,
    questions_csv_path,
    tagged_questions_csv_path,
)
from src.subject_plan import variant_in_scope

logger = logging.getLogger(__name__)

_CLASSIFICATION_KEYS = ("topic", "subtopic", "command_word", "difficulty")
_DIFFICULTIES = {"easy", "medium", "hard"}
_QUESTION_REQUIRED_COLUMNS = {
    "question_id",
    "subject",
    "filename",
    "paper",
    "year",
    "session",
    "variant",
    "question_number",
    "question_text",
    "subquestions",
}
_PAIR_REQUIRED_COLUMNS = {
    "subject",
    "paper",
    "year",
    "session",
    "variant",
    "qp_text",
    "ms_text",
}


def _load_subject_name(subject: str, plan_path: Path = Path("config/subject_plan.json")) -> str:
    if not plan_path.exists():
        return str(subject)

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    for item in payload.get("subjects", []):
        if str(item.get("code", "")).strip() == str(subject):
            return str(item.get("name", subject)).strip() or str(subject)
    return str(subject)


def _parse_json_response(response_text: str) -> Any:
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)

    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("Gemini response did not contain a valid JSON object")


def _validate_classification(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("classification response was not a JSON object")

    missing = [key for key in _CLASSIFICATION_KEYS if key not in value]
    if missing:
        raise ValueError(f"classification response missing keys: {', '.join(missing)}")

    result = {key: str(value[key]).strip() for key in _CLASSIFICATION_KEYS}
    result["difficulty"] = result["difficulty"].lower()
    if result["difficulty"] not in _DIFFICULTIES:
        raise ValueError(f"invalid difficulty: {result['difficulty']}")
    if any(not result[key] for key in _CLASSIFICATION_KEYS):
        raise ValueError("classification response contained an empty field")
    return result


def _validate_mark_points(value: Any) -> list[str]:
    if not isinstance(value, dict) or not isinstance(value.get("points"), list):
        raise ValueError("mark-scheme response must be an object with a points list")
    points = [str(point).strip() for point in value["points"]]
    if any(not point for point in points):
        raise ValueError("mark-scheme response contained an empty point")
    return points


def _classification_prompt(subject_name: str, label: str | None, text: str, marks: object) -> str:
    label_line = label or "top-level question"
    return f"""You are classifying one CAIE {subject_name} question for a study database.

Infer the syllabus topic and subtopic from the question. Do not use a fixed topic list; choose a concise, natural name that best fits the syllabus area. Identify the command word and estimate difficulty.

Return ONLY one valid JSON object with exactly these keys:
{{"topic": "...", "subtopic": "...", "command_word": "...", "difficulty": "easy|medium|hard"}}
Do not use Markdown fences or add any explanation.

Label: {label_line}
Marks: {marks}
Question text:
{text}
""".strip()


def _mark_scheme_prompt(subject_name: str, paper: str, text: str) -> str:
    return f"""You are extracting marking points from a CAIE {subject_name} mark scheme for paper {paper}.

Extract the discrete points that could earn marks. Keep each point short and faithful to the mark scheme. Do not invent points or include examiner commentary.

Return ONLY one valid JSON object with exactly this shape:
{{"points": ["short marking point", "another marking point"]}}
Do not use Markdown fences or add any explanation.

Mark scheme text:
{text}
""".strip()


def _response_text(response: Any) -> str:
    response_text = getattr(response, "text", None)
    if not response_text:
        raise ValueError("Gemini returned an empty response")
    return str(response_text)


class _RateLimiter:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self.last_call_at: float | None = None

    def wait(self) -> None:
        if self.last_call_at is not None:
            elapsed = time.monotonic() - self.last_call_at
            remaining = self.delay_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self.last_call_at = time.monotonic()


def _call_json(
    model: Any,
    prompt: str,
    validator: Callable[[Any], Any],
    item_label: str,
    rate_limiter: _RateLimiter,
) -> Any | None:
    for attempt in range(2):
        try:
            rate_limiter.wait()
            response = model.generate_content(prompt)
            return validator(_parse_json_response(_response_text(response)))
        except Exception as exc:
            if attempt == 0:
                logger.warning("Invalid Gemini response for %s; retrying once: %s", item_label, exc)
            else:
                logger.warning("Skipping %s after two invalid Gemini responses: %s", item_label, exc)
    return None


def _decode_subquestions(value: object, question_id: str) -> list[dict[str, object]]:
    if pd.isna(value):
        return []
    try:
        decoded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError) as exc:
        logger.warning("Could not decode subquestions for %s: %s", question_id, exc)
        return []
    if not isinstance(decoded, list):
        logger.warning("Subquestions for %s were not a JSON list", question_id)
        return []
    return [item for item in decoded if isinstance(item, dict)]


def _load_questions(
    subject: str,
    path: Path,
    allowed_variants: set[str] | None = None,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing questions CSV: {path}. Run segmentation first.")
    questions = pd.read_csv(path)
    missing = _QUESTION_REQUIRED_COLUMNS.difference(set(questions.columns))
    if missing:
        raise ValueError(f"Questions CSV missing required columns: {', '.join(sorted(missing))}")
    filtered = questions[questions["subject"].astype(str).str.strip() == str(subject)].copy()
    if allowed_variants is not None:
        filtered = filtered[
            filtered["variant"].map(lambda value: variant_in_scope(value, allowed_variants))
        ]
    return filtered


def _load_pairs(
    subject: str,
    path: Path,
    allowed_variants: set[str] | None = None,
) -> pd.DataFrame:
    if not path.exists():
        logger.warning("Missing QP/MS pairs CSV: %s; mark-scheme points will be empty", path)
        return pd.DataFrame()
    pairs = pd.read_csv(path)
    missing = _PAIR_REQUIRED_COLUMNS.difference(set(pairs.columns))
    if missing:
        raise ValueError(f"QP/MS pairs CSV missing required columns: {', '.join(sorted(missing))}")
    filtered = pairs[pairs["subject"].astype(str).str.strip() == str(subject)].copy()
    if allowed_variants is not None:
        filtered = filtered[
            filtered["variant"].map(lambda value: variant_in_scope(value, allowed_variants))
        ]
    return filtered


def _match_key(row: pd.Series) -> tuple[str, str, int, str, str]:
    return (
        str(row["subject"]),
        str(row["paper"]),
        int(row["year"]),
        str(row["session"]),
        str(row["variant"]),
    )


def _prepare_model(model_name: str) -> Any:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to .env before running tag.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name=model_name)


def tag_questions(
    subject: str,
    questions_csv: Path | None = None,
    pairs_csv: Path | None = None,
    output_csv: Path | None = None,
    model_name: str = "gemini-2.5-flash",
    limit: int | None = None,
    dry_run: bool = False,
    delay_seconds: float = 1.0,
    model: Any | None = None,
    allowed_variants: set[str] | None = None,
) -> pd.DataFrame:
    """Classify segmented questions and extract points from matched mark schemes."""

    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    questions_csv = questions_csv or questions_csv_path(subject)
    pairs_csv = pairs_csv or qp_ms_pairs_csv_path(subject)
    output_csv = output_csv or tagged_questions_csv_path(subject)
    questions = _load_questions(subject, questions_csv, allowed_variants)
    if limit is not None:
        questions = questions.head(limit)
    pairs = _load_pairs(subject, pairs_csv, allowed_variants)

    classification_jobs: list[tuple[int, str | None, str, object, str]] = []
    for row_index, row in questions.iterrows():
        subquestions = _decode_subquestions(row["subquestions"], str(row["question_id"]))
        if subquestions:
            for subquestion in subquestions:
                classification_jobs.append(
                    (
                        row_index,
                        str(subquestion.get("label", "")) or None,
                        str(subquestion.get("text", "")).strip(),
                        subquestion.get("marks", ""),
                        str(row["question_id"]),
                    )
                )
        else:
            classification_jobs.append(
                (
                    row_index,
                    None,
                    str(row["question_text"]).strip(),
                    row.get("marks", ""),
                    str(row["question_id"]),
                )
            )

    subject_name = _load_subject_name(subject)
    classification_results: dict[int, list[dict[str, object]]] = {
        row_index: [] for row_index in questions.index
    }
    if not dry_run and classification_jobs:
        model = model or _prepare_model(model_name)
    rate_limiter = _RateLimiter(delay_seconds)

    for job_number, (row_index, label, text, marks, question_id) in enumerate(classification_jobs, start=1):
        prompt = _classification_prompt(subject_name, label, text, marks)
        if dry_run:
            print(f"\n--- CLASSIFICATION PROMPT {job_number}/{len(classification_jobs)} ({question_id}) ---\n{prompt}")
            continue
        result = _call_json(
            model,
            prompt,
            _validate_classification,
            f"classification {question_id} {label or 'top-level'}",
            rate_limiter,
        )
        if result is not None:
            classification_results[row_index].append(
                {"label": label, "text": text, "marks": marks, **result}
            )

    pair_points: dict[tuple[str, str, int, str, str], list[str]] = {}
    pair_jobs = list(pairs.iterrows())
    if limit is not None:
        pair_jobs = pair_jobs[:limit]
    if not dry_run and pair_jobs:
        model = model or _prepare_model(model_name)

    for job_number, (_, pair) in enumerate(pair_jobs, start=1):
        ms_text = "" if pd.isna(pair["ms_text"]) else str(pair["ms_text"])
        prompt = _mark_scheme_prompt(subject_name, str(pair["paper"]), ms_text)
        pair_key = _match_key(pair)
        item_label = f"mark scheme {pair.get('ms_filename', pair_key)}"
        if dry_run:
            print(f"\n--- MARK-SCHEME PROMPT {job_number}/{len(pair_jobs)} ({item_label}) ---\n{prompt}")
            continue
        result = _call_json(model, prompt, _validate_mark_points, item_label, rate_limiter)
        if result is not None:
            pair_points[pair_key] = result

    output_rows: list[dict[str, object]] = []
    for row_index, row in questions.iterrows():
        results = classification_results[row_index]
        top_level = results[0] if len(results) == 1 and results[0]["label"] is None else {}
        key = _match_key(row)
        output_row = row.to_dict()
        output_row.update(
            {
                "topic": top_level.get("topic", ""),
                "subtopic": top_level.get("subtopic", ""),
                "command_word": top_level.get("command_word", ""),
                "difficulty": top_level.get("difficulty", ""),
                "subquestion_tags": json.dumps(results, ensure_ascii=False),
                "mark_scheme_points": json.dumps(pair_points.get(key, []), ensure_ascii=False),
            }
        )
        output_rows.append(output_row)

    output_columns = list(questions.columns) + [
        "topic",
        "subtopic",
        "command_word",
        "difficulty",
        "subquestion_tags",
        "mark_scheme_points",
    ]
    tagged = pd.DataFrame(output_rows, columns=output_columns)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    tagged.to_csv(output_csv, index=False, encoding="utf-8")
    if dry_run:
        print(f"Dry run skipped Gemini calls; wrote prompt preview output to {output_csv}")
    else:
        print(f"Tagged {len(tagged)} questions into {output_csv}")
    return tagged


if __name__ == "__main__":
    print("Use `python -m src.cli tag --subject <code>` to tag questions.")
