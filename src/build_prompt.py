from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.paths import blueprint_json_path, generated_prompt_md_path, representative_questions_csv_path


def _format_examples(samples: pd.DataFrame) -> str:
    if samples.empty:
        return "- No representative questions found yet."

    lines: list[str] = []
    for idx, row in enumerate(samples.itertuples(index=False), start=1):
        text = str(row.question_text).strip().replace("\n", " ")
        if len(text) > 260:
            text = f"{text[:257]}..."
        lines.append(f"- Example {idx} ({row.paper}, {row.year}): {text}")
    return "\n".join(lines)


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

    blueprint = json.loads(blueprint_json.read_text(encoding="utf-8"))
    samples = pd.read_csv(representative_csv)
    example_block = _format_examples(samples)

    scaffold = blueprint.get("scaffold", {})
    scaffold_lines: list[str] = []
    for paper, details in sorted(scaffold.items()):
        question_count = details.get("target_question_count", "N/A")
        total_marks = details.get("target_total_marks", "N/A")
        scaffold_lines.append(
            f"- {paper.upper()}: target {question_count} questions, {total_marks} total marks"
        )

    scaffold_block = "\n".join(scaffold_lines) if scaffold_lines else "- No paper scaffold available yet."

    prompt = f"""# {subject} Practice Paper Generation Prompt

You are generating a CAIE {subject} practice paper from extracted and segmented past-paper data.

## Blueprint Scaffold
{scaffold_block}
- Constraint: Keep wording and cognitive demand aligned to authentic {subject} papers.

## Representative Examples
{example_block}

## Output Requirements
- Produce one full draft practice paper.
- Keep question styles realistic and varied.
- Provide a mark allocation per question.
- Avoid copying any one past question verbatim.
"""

    output_prompt_md.parent.mkdir(parents=True, exist_ok=True)
    output_prompt_md.write_text(prompt, encoding="utf-8")
    print(f"Wrote prompt scaffold to {output_prompt_md}")
    return prompt


if __name__ == "__main__":
    print("Use `python -m src.cli build-prompt --subject <code>` to build prompts.")
