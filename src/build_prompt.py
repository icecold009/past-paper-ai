from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from src.paths import blueprint_json_path, generated_prompt_md_path, representative_questions_csv_path


_AUTO_BLOCK_START = "<!-- AUTO-DATA-START -->"
_AUTO_BLOCK_END = "<!-- AUTO-DATA-END -->"

_SUBJECT_PAPER_MARKS: dict[str, dict[str, int]] = {
    "9618": {"p1": 75, "p2": 75},
    "9702": {"p1": 40, "p2": 60},
    "9709": {"p1": 75, "p5": 50},
    "9231": {"p1": 75, "p4": 50},
}

_MOCK_EXAMPLE_TEXTS = {
    "1. Explain two reasons why a CPU uses cache memory. [4]",
    "2. Describe one advantage of optical storage over magnetic storage. [2]",
    "1. Write pseudocode to validate a user input in the range 1 to 100. [5]",
    "2. State one use of an array in this program. [1]",
}


def _format_examples(samples: pd.DataFrame) -> str:
    if samples.empty:
        return "- No representative questions found yet."

    filtered = samples.copy()
    if "question_text" in filtered.columns:
        normalized = filtered["question_text"].astype(str).str.strip()
        filtered = filtered[~normalized.isin(_MOCK_EXAMPLE_TEXTS)]

    if filtered.empty:
        return "- Representative examples are currently mock placeholders. Add real PDFs and rerun extraction to populate subject-authentic examples."

    lines: list[str] = []
    for idx, row in enumerate(filtered.itertuples(index=False), start=1):
        text = str(row.question_text).strip().replace("\n", " ")
        if len(text) > 260:
            text = f"{text[:257]}..."
        lines.append(f"- Example {idx} ({row.paper}, {row.year}): {text}")
    return "\n".join(lines)


def _strip_existing_auto_block(text: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(_AUTO_BLOCK_START)}.*?{re.escape(_AUTO_BLOCK_END)}\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text).rstrip()


def build_prompt(
    subject: str,
    blueprint_json: Path | None = None,
    representative_csv: Path | None = None,
    output_prompt_md: Path | None = None,
) -> str:
    if blueprint_json is None:
        blueprint_json = blueprint_json_path(subject)
    if representative_csv is None:
        representative_csv = representative_questions_csv_path(subject)
    if output_prompt_md is None:
        output_prompt_md = generated_prompt_md_path(subject)

    if not blueprint_json.exists():
        raise FileNotFoundError(
            f"Missing blueprint JSON: {blueprint_json}. Run analysis first."
        )

    if not representative_csv.exists():
        raise FileNotFoundError(
            f"Missing representative CSV: {representative_csv}. Run analysis first."
        )

    if output_prompt_md.exists():
        base_prompt = output_prompt_md.read_text(encoding="utf-8").strip()
    else:
        generic_prompt = output_prompt_md.parent / "practice_paper_prompt.md"
        if generic_prompt.exists():
            base_prompt = generic_prompt.read_text(encoding="utf-8").strip()
        else:
            base_prompt = (
                f"# {subject} Practice Paper Generation Prompt\n\n"
                f"You are generating a CAIE {subject} practice paper."
            )

    blueprint = json.loads(blueprint_json.read_text(encoding="utf-8"))
    samples = pd.read_csv(representative_csv)
    example_block = _format_examples(samples)

    scaffold = blueprint.get("scaffold", {})
    subject_marks = _SUBJECT_PAPER_MARKS.get(subject, {})
    scaffold_lines: list[str] = []
    for paper, details in sorted(scaffold.items()):
        question_count = details.get("target_question_count", "N/A")
        total_marks = subject_marks.get(paper.lower(), details.get("target_total_marks", "N/A"))
        scaffold_lines.append(
            f"- {paper.upper()}: target {question_count} questions, {total_marks} total marks"
        )

    scaffold_block = "\n".join(scaffold_lines) if scaffold_lines else "- No paper scaffold available yet."

    auto_block = f"""
{_AUTO_BLOCK_START}
## Data-Driven Addendum (Auto-Generated)

Use this block as additional evidence from extracted data. Keep all subject-specific syllabus constraints from the handcrafted prompt above.

### Blueprint Scaffold Snapshot
{scaffold_block}

### Representative Examples From Extracted Data
{example_block}
{_AUTO_BLOCK_END}
""".strip()

    prompt = f"{_strip_existing_auto_block(base_prompt)}\n\n{auto_block}\n"

    output_prompt_md.parent.mkdir(parents=True, exist_ok=True)
    output_prompt_md.write_text(prompt, encoding="utf-8")
    print(f"Merged handcrafted base prompt with data addendum into {output_prompt_md}")
    return prompt


if __name__ == "__main__":
    print("Use `python -m src.cli build-prompt --subject <code>` to build prompts.")
