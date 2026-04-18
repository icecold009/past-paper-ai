from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src.paths import generated_paper_md_path, generated_prompt_md_path


def generate_practice_paper(
    subject: str,
    prompt_path: Path | None = None,
    output_path: Path | None = None,
    model_name: str = "gemini-1.5-flash",
    dry_run: bool = False,
) -> Path:
    if prompt_path is None:
        prompt_path = generated_prompt_md_path(subject)
    if output_path is None:
        output_path = generated_paper_md_path(subject)

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Missing prompt file: {prompt_path}. Run build-prompt first."
        )

    prompt = prompt_path.read_text(encoding="utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        dry_run_content = (
            f"# {subject} Practice Paper Draft (Dry Run)\n\n"
            "Dry-run mode skipped Gemini generation.\n\n"
            "## Prompt Preview\n\n"
            f"{prompt[:2500]}\n"
        )
        output_path.write_text(dry_run_content, encoding="utf-8")
        return output_path

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to .env before running generate.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name=model_name)
    response = model.generate_content(prompt)
    generated_text = getattr(response, "text", None)
    if not generated_text:
        raise RuntimeError("Gemini returned an empty response.")

    output_path.write_text(generated_text, encoding="utf-8")
    return output_path
