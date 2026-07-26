# AGENTS.md

Instructions for any AI coding agent (Codex, Claude Code, etc.) working in this repository.

## What this repo is

`past-paper-ai` is a Python pipeline that turns CAIE (Cambridge International A Level) past-paper PDFs into structured data, then generates practice papers with Gemini. It is being extended into a personalized study web app (see `docs/plan.md` and `docs/implementation_prompts.md` for the full roadmap).

Current subjects: `9618` Computer Science, `9709` Mathematics, `9231` Further Mathematics, `9702` Physics.

## Read this before changing anything

1. `README.md`
2. `config/subject_plan.json`
3. `src/cli.py` — orchestration entry point, read this before any individual module
4. `src/paths.py` — where every artifact lives
5. `src/subject_plan.py` — subject/paper config + hardcoded marks table
6. `src/utils.py` — `parse_caie_filename`, the filename metadata parser most stages depend on
7. Then the pipeline modules in execution order: `extract_pdfs.py` → `segment_questions.py` → `analyze_questions.py` → `build_prompt.py` → `generate_paper.py`
8. `docs/plan.md` — target architecture (DB schema, mastery model, app layers)
9. `docs/implementation_prompts.md` — the phased build plan; check which phase is currently in progress before starting new work

Do not read files alphabetically or jump straight to editing — the pipeline stages depend on each other's output schemas.

## Pipeline data lineage

```
data/raw_pdfs/*.pdf
    ↓ extract_pdfs.py
data/extracted/<subject>_pages.csv
    ↓ segment_questions.py
data/extracted/<subject>_questions.csv
    ↓ analyze_questions.py
outputs/<subject>_question_stats.csv
outputs/<subject>_representative_questions.csv
outputs/<subject>_blueprint_scaffold.json
    ↓ build_prompt.py
prompts/<subject>_practice_paper_prompt.md
    ↓ generate_paper.py
outputs/<subject>_practice_paper_draft.md
```

`cli.py` connects these stages. `run` executes `extract → segment → analyze → build-prompt` — it does **not** call `generate` (that's separate, and costs API quota).

## Invariants — do not break these without explicit instruction

- **Subject codes are strings** (`"9618"`, not `9618`).
- **Paper identifiers are lowercase** (`p1`, `p2`, `p5`).
- **Filenames are metadata.** Required format: `<subject>_<paper>_<year>_<session>_<variant>_<type>.pdf` (e.g. `9618_p1_2023_mj_11_qp.pdf`). Session codes: `mj`/`on`/`fm`. Doc types: `qp`/`ms`. Many stages depend on `parse_caie_filename` in `src/utils.py` — check it before adding new filename handling logic.
- **Generated output directories are created automatically** (`mkdir(parents=True, exist_ok=True)`) before writing — keep this pattern in new code.
- **Pipeline stages fail loudly on missing upstream data**, except when `--mock` is explicitly passed. Don't silently fabricate results.
- **Existing CSV/JSON columns are additive, not destructive**, when extending schemas — downstream consumers (`analyze_questions.py`, `build_prompt.py`) shouldn't break because a new column was added upstream. If a phase explicitly says to migrate a schema, that's the exception.
- **`SUBJECT_PAPER_MARKS` in `src/subject_plan.py` and `config/subject_plan.json` are two separate sources of config** — adding a subject requires updating both.

## Known limitations (don't accidentally "fix" these as a side effect of unrelated work — they're tracked separately in docs/plan.md)

- Segmentation is regex-based; complex multi-column/math-heavy layouts can fail.
- PDF parsing is text-only — no OCR, no diagram/table understanding.
- Mark schemes (`doc_type == "ms"`) are extracted but not yet used downstream (this is being fixed in the current roadmap — see Phase 2/3 of `docs/implementation_prompts.md`).
- No topic/command-word/difficulty tagging yet (Phase 3).
- No database yet — everything is CSV/JSON on disk (Phase 4 introduces Postgres).

## Testing workflow

Always validate a change with mock data before touching real data:

```bash
python -m src.cli run --mock
python -m src.cli generate --dry-run
```

Then inspect `data/extracted/`, `outputs/`, and `prompts/` by hand. When working with real PDFs, run stages one at a time and inspect the CSV output after each — do not assume a stage worked just because it exited without error. In particular:

- After `extract`: open `<subject>_pages.csv`, check the `text` column for garbled/missing content.
- After `segment`: open `<subject>_questions.csv`, check that one real exam question became one row, subparts are captured, and text didn't split/merge incorrectly across page boundaries.
- After any Gemini-calling step (`tag`, `generate`): spot-check a sample of outputs by hand before trusting a full batch run — bad tags or bad grading logic silently degrade every feature built on top.

## Environment

`.env` at repo root, loaded via `python-dotenv`:
```
GEMINI_API_KEY=...
DATABASE_URL=...   # added in Phase 4, see docs/plan.md
```
Never commit real keys.

## Current build phase

Check `docs/implementation_prompts.md` for the phase list. Update this section as phases land:

Each phase prompt assumes the previous phase is merged and working. Do not batch multiple phases into one agent session; the manual-check steps between phases are intentional and mirror the handoff document's debugging philosophy: trace issues backward through the pipeline, not forward.

Phase 3 (Gemini tagging) warrants especially careful manual review. Bad topic or command-word tags can quietly degrade every feature built after it.

- [ ] Phase 1 — Subquestion + marks parsing (`segment_questions.py`)
- [ ] Phase 2 — QP ↔ MS matching
- [ ] Phase 3 — Gemini tagging pass (topics, command words, mark-scheme points)
- [ ] Phase 4 — Postgres schema + ingestion loader
- [ ] Phase 5 — FastAPI backend (questions + answer grading)
- [ ] Phase 6 — React frontend (answer flow)
- [ ] Phase 7 — Mastery dashboard
- [ ] Phase 8 — Weak-spot paper generation

Do not start a phase whose predecessor is unchecked — each phase's output is the next phase's input.
