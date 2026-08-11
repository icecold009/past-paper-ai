# AGENTS.md

Instructions for any AI coding agent (Codex, Claude Code, etc.) working in this repository.

## What this repo is

`past-paper-ai` is a Python pipeline that turns CAIE (Cambridge International A Level) past-paper PDFs into structured data, then generates practice papers with Gemini. It is being extended into a personalized study web app (see `docs/06_implementation_plan.md` and `docs/08_backlog.md` for the current roadmap).

Current subjects: `9618` Computer Science, `9709` Mathematics, `9231` Further Mathematics, `9702` Physics.

## Read this before changing anything

1. `README.md`
2. `config/subject_plan.json`
3. `src/cli.py` — orchestration entry point, read this before any individual module
4. `src/paths.py` — where every artifact lives
5. `src/subject_plan.py` — subject/paper config + hardcoded marks table
6. `src/utils.py` — `parse_caie_filename`, the filename metadata parser most stages depend on
7. Then the pipeline modules in execution order: `extract_pdfs.py` → `segment_questions.py` → `analyze_questions.py` → `build_prompt.py` → `generate_paper.py`
8. `docs/06_implementation_plan.md` — target architecture and phased build plan
9. `docs/08_backlog.md` — current blockers, acceptance criteria, and execution order
10. `docs/09_api_v1.md` — implemented API slice and explicit v1 limitations

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
- The checked-in sample data contains QP rows but no MS rows, so real QP/MS coverage and mark-scheme quality are not yet demonstrated.
- Gemini tagging code exists, but real tagging and the required 15–20-question syllabus review remain blocked on representative matched data and `GEMINI_API_KEY`.
- The v1 FastAPI service and React frontend exist, but authentication, ownership/RLS, persistent practice sessions, school curriculum mapping, and production deployment remain incomplete.

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
DATABASE_URL=...   # used by the SQLAlchemy/Alembic data layer
```
Never commit real keys.

## Current build phase

The current implementation status is maintained in `docs/06_implementation_plan.md` and `docs/08_backlog.md`. Update this section as phases land:

Each phase assumes the previous phase is merged and working. Do not batch later phases into one agent session; manual gates are intentional and preserve backward-traceable evidence.

Phase 3 (Gemini tagging) warrants especially careful manual review. Bad topic or command-word tags can quietly degrade every feature built after it.

This is the highest-leverage checkpoint: manually review at least 15–20 tagged questions against the actual syllabus before running tagging on the full dataset. Do not treat schema validation or successful API responses as evidence that the tags are correct.

- [x] Phase 1 — Extraction/segmentation code and tests; real-paper validation remains open.
- [x] Phase 2 — QP/MS matching code and tests; the current fixture has no MS rows.
- [ ] Phase 3 — Real Gemini tagging sample and mandatory 15–20-question syllabus review.
- [x] Phase 4 — SQLAlchemy/Alembic schema and idempotent local ingestion; disposable PostgreSQL validation remains open.
- [ ] Phase 5 — School curriculum map and personalization model.
- [x] Phase 6 — FastAPI v1 slice for subjects, questions, attempts, mastery, and weak-spot papers; auth and full contract remain open.
- [x] Phase 7 — React v1 slice for subject selection, mastery, answering, grading feedback, and generated-paper display; onboarding and authenticated persistence remain open.
- [ ] Phase 8 — Authentication, school permissions, and RLS.
- [ ] Phase 9 — Practice-session persistence and idempotent submissions.
- [ ] Phase 10 — Mark-scheme-aware grading and feedback policy.
- [ ] Phase 11 — Mastery, weakness profiles, and explainable recommendations.
- [ ] Phase 12 — Production deployment and operations.

Do not run full-dataset tagging or enable chapter recommendations until representative real inputs and the manual review gate pass.
