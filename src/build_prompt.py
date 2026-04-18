from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.paths import BLUEPRINT_JSON, GENERATED_PROMPT_MD, REPRESENTATIVE_QUESTIONS_CSV


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
    blueprint_json: Path = BLUEPRINT_JSON,
    representative_csv: Path = REPRESENTATIVE_QUESTIONS_CSV,
    output_prompt_md: Path = GENERATED_PROMPT_MD,
) -> str:
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
    p1 = scaffold.get("p1", {})
    p2 = scaffold.get("p2", {})

    prompt = f"""# 9618 Practice Paper Generation Prompt

You are generating a CAIE 9618 practice paper from extracted and segmented past-paper data.

## Blueprint Scaffold
- Paper 1: target {p1.get('target_question_count', 'N/A')} questions, {p1.get('target_total_marks', 'N/A')} total marks
- Paper 2: target {p2.get('target_question_count', 'N/A')} questions, {p2.get('target_total_marks', 'N/A')} total marks
- Constraint: Keep wording and cognitive demand aligned to authentic 9618 papers.

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
    build_prompt()
