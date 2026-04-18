# past-paper-ai

A free local project to generate CAIE practice papers from past papers.

## Goal
Build a simple Python workflow that:
1. Stores past paper PDFs for multiple CAIE subjects.
2. Extracts text from those PDFs.
3. Sends cleaned past-paper content to a free Gemini API model.
4. Generates a realistic practice paper for revision.

## Project structure

```text
past-paper-ai/
  src/
    cli.py
    paths.py
    utils.py
    subject_plan.py
    extract_pdfs.py
    segment_questions.py
    analyze_questions.py
    build_prompt.py
    generate_paper.py
  config/
    subject_plan.json
  data/
    raw_pdfs/
      ... (any nested folders)
    extracted/
  outputs/
  prompts/
  .env
```

## File naming rules
Rename PDFs exactly like this:

```text
9618_p1_2023_mj_11_qp.pdf
9618_p1_2023_mj_11_ms.pdf
9702_p4_2022_on_42_qp.pdf
9702_p4_2022_on_42_ms.pdf
```

### Meaning
- `9618` = subject code
- `p1` / `p2` / `p3` / `p4` ... = paper number
- `2023` = year
- `mj` / `on` / `fm` = May/June, Oct/Nov, Feb/March
- `11 12 13` / `21 22 23` / ... = variant code
- `qp` = question paper
- `ms` = mark scheme

## Setup
Open a terminal in the project folder and install the libraries:

```bash
pip install -r requirements.txt
```

## Default subject plan
The project now includes a default plan in `config/subject_plan.json`:
- 9618 (Computer Science): p1, p2
- 9709 (Mathematics): p1, p5
- 9231 (Further Mathematics): p1, p4
- 9702 (Physics): p1, p2

If you run commands without `--subject`, the CLI uses this plan by default.

## Step-by-step workflow

### 1. Download papers
Download CAIE PDFs for your target subjects.

Put them anywhere under `data/raw_pdfs/`.

### 2. Validate filenames and folders
Run:

```bash
python -m src.cli validate
```

Or validate specific subjects:

```bash
python -m src.cli validate --subject 9618 --subject 9702
```

By default, `validate` also respects configured papers in `config/subject_plan.json`.

### 3. Extract text
Run:

```bash
python -m src.cli extract
```

Or extract specific subjects:

```bash
python -m src.cli extract --subject 9618 --subject 9702
```

If no `--subject` is provided, extraction uses all subjects from `config/subject_plan.json`.

This creates:

```text
data/extracted/<subject>_pages.csv
```

This first pass extracts one row per PDF page, keeping the filename metadata and raw page text for later question segmentation.

### 4. Segment questions
Run:

```bash
python -m src.cli segment
```

Or segment specific subjects:

```bash
python -m src.cli segment --subject 9618 --subject 9702
```

This creates:

```text
data/extracted/<subject>_questions.csv
```

### 5. Build analysis artifacts
Run:

```bash
python -m src.cli analyze
```

Or analyze specific subjects:

```bash
python -m src.cli analyze --subject 9618 --subject 9702
```

This creates:

```text
outputs/<subject>_question_stats.csv
outputs/<subject>_representative_questions.csv
outputs/<subject>_blueprint_scaffold.json
```

### 6. Build prompt scaffold
Run:

```bash
python -m src.cli build-prompt
```

Or build prompts for specific subjects:

```bash
python -m src.cli build-prompt --subject 9618 --subject 9702
```

This creates:

```text
prompts/<subject>_practice_paper_prompt.md
```

The blueprint scaffold in prompts is now generated dynamically from configured/observed papers per subject.

### 7. Add your Gemini API key
Create a file called `.env` in the project root before running generation:

```env
GEMINI_API_KEY=your_api_key_here
```

### 8. Generate paper draft
Run:

```bash
python -m src.cli generate
```

Default model is `gemini-2.5-flash` (override with `--model`).

Run for specific subjects:

```bash
python -m src.cli generate --subject 9618 --subject 9702
```

Run without Gemini API calls (dry run):

```bash
python -m src.cli generate --dry-run
```

This creates:

```text
outputs/<subject>_practice_paper_draft.md
```

### Optional: run pipeline stages 1–4 at once

```bash
python -m src.cli run
```

This runs `extract → segment → analyze → build-prompt` only. Run `generate` separately after adding your API key (step 7 above).

By default, non-mock `run` now fails if no pages are extracted for a subject, to avoid silently producing empty artifacts.

Run full flow for selected subjects:

```bash
python -m src.cli run --subject 9618 --subject 9702
```

If you have not added PDFs yet, you can still test downstream stages with mock rows:

```bash
python -m src.cli segment --mock
# or full run mode
python -m src.cli run --mock
```

In mock mode, the generated sample papers align with each subject's configured paper list.

## Current status
At the moment, the project is set up for:
- Multiple CAIE subjects (using subject-coded filenames)
- Any paper number format `p<digit+>`
- Local PDF extraction
- Question segmentation and analysis scaffolding
- Prompt scaffold generation

## Notes
- This is meant to be fully free.
- You can run one subject or multiple subjects in one command.
- More past papers usually improves the generated practice paper.
- Mark schemes are useful later for answer style and checking patterns.
