# Technical Requirements Document

## 1. Purpose and status

This document is the technical reference for the current `past-paper-ai` repository and the target architecture it enables.

- Reviewed against repository: 2026-07-26
- Product target: a school-focused Cambridge Grades 8–12 learning system that diagnoses weak subjects/chapters and serves targeted activities
- Current architecture: local-first Python batch pipeline with CSV/JSON artifacts
- Database phase: SQLAlchemy models, Alembic migration, and idempotent ingestion are implemented and locally verified with SQLite
- Not yet implemented: FastAPI, frontend, production Postgres deployment, auth, RLS, queues, observability platform, and CDN

The implementation plan is intentionally phased. A future service must consume stable intermediate artifacts and database contracts rather than bypassing source validation.

## 2. Architecture overview

```text
data/raw_pdfs/
      │
      ▼
validate ──► src/utils.py + subject plan checks
      │
      ▼
extract ──► data/extracted/<subject>_pages.csv
      │
      ▼
segment ──► data/extracted/<subject>_questions.csv
      │              (top-level questions, subquestions JSON, marks)
      ├────────────► analyze ──► outputs/<subject>_question_stats.csv
      │                         outputs/<subject>_representative_questions.csv
      │                         outputs/<subject>_blueprint.json
      │
      ▼
match ──► data/extracted/<subject>_qp_ms_pairs.csv
      │
      ▼
tag ──► data/extracted/<subject>_tagged_questions.csv
      │
      ├──► build-prompt ──► prompts/<subject>_practice_paper_prompt.md
      ├──► generate ──► generated practice-paper output
      └──► ingest ──► PostgreSQL/SQLite tables
```

The model/API application planned for later phases should read reviewed database records and a school-approved curriculum map. It should not call Gemini for every student request. Runtime recommendations should use stored evidence and bounded business rules; model calls may enrich content offline or provide carefully constrained explanations.

## 3. Repository map

```text
config/
  subject_plan.json                 supported subjects, papers, marks, durations
  curriculum/                       planned school grade/stage/chapter mappings
data/
  raw_pdfs/                         source PDFs; local input, usually ignored by Git
  extracted/                        page, question, pair, and tag CSV artifacts
outputs/                            analysis artifacts and generated outputs
prompts/                            generated prompt documents
src/
  cli.py                            argparse command dispatcher
  paths.py                          canonical project/data/output paths
  subject_plan.py                   subject-plan loading and validation
  utils.py                          filename parsing, normalization, shared helpers
  extract.py                        configured extraction orchestration
  extract_pdfs.py                   PDF page extraction
  segment_questions.py              top-level/sub-question/mark segmentation
  match_mark_schemes.py             QP/MS matching by filename metadata
  tag_questions.py                  bounded Gemini batch enrichment
  analyze_questions.py              question distribution analysis
  build_prompt.py                   practice-paper prompt construction
  generate_paper.py                 Gemini-assisted paper generation
  db/
    models.py                       SQLAlchemy schema
    session.py                       DATABASE_URL/session setup
    ingest.py                       tagged CSV and pair ingestion
tests/                              unit tests and mock fixtures
alembic/
  env.py                            migration runtime configuration
  versions/0001_initial_schema.py   initial relational schema
alembic.ini                         Alembic configuration
pyproject.toml                      package metadata and console entry point
requirements.txt                    runtime dependency list
```

## 4. Runtime and dependency requirements

### Supported runtime

- Python 3.11 or newer (`pyproject.toml` declares `>=3.11`).
- A project virtual environment is recommended.
- PowerShell commands should use the repository’s `.venv` explicitly when available.

### Current libraries

- `pandas`: tabular intermediate data and CSV I/O
- `pdfplumber`: PDF text extraction
- `python-dotenv`: local `.env` configuration
- `google-generativeai`: Gemini batch tagging and generation
- `SQLAlchemy`: ORM and database model layer
- `Alembic`: schema migrations
- `psycopg[binary]`: PostgreSQL driver
- `pytest`: unit tests

The dependency list is duplicated in `requirements.txt` and `pyproject.toml`; changes must keep both aligned until one becomes the sole installation source.

## 5. Configuration contracts

### Subject plan

`config/subject_plan.json` is the configuration source for:

- subject code and display name;
- papers in scope;
- maximum marks per paper;
- duration in minutes;
- prompt/context information.

For the product target, the configuration layer must be extended with or linked to:

- Cambridge stage and school grade band, including Grades 8–12;
- syllabus revision and academic year;
- school-approved subject and chapter identifiers;
- mappings from chapter names used by teachers to source-paper topics/subtopics;
- whether a content unit is available for diagnostic, targeted practice, exam practice, or teacher review.

Grade is not safely inferable from a paper filename. It must be supplied by the school curriculum configuration and validated against the content scope.

Current subjects are 9618, 9709, 9231, and 9702. A subject code should be treated as a string because leading zeros would be meaningful for other syllabuses.

### Environment

`.env` is local-only and ignored by Git. `.env.example` documents the shape:

```text
GEMINI_API_KEY=your_key_here
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/past_paper_ai
```

Secrets must not appear in source, CSVs, prompts, logs, commits, or issue reports.

### Filename contract

The shared key is parsed from:

```text
<subject>_<paper>_<year>_<mj|on|fm>_<variant>_<qp|ms>.pdf
```

The normalized metadata fields are `subject`, `paper`, `year`, `session`, `variant`, and `doc_type`. `src/utils.py` is the source of truth for parsing and session normalization. Do not create a second parser in a downstream phase.

## 6. Intermediate data contracts

### 6.1 Page CSV

`data/extracted/<subject>_pages.csv` contains one row per extracted PDF page. It currently combines QP and MS pages when both are present. Important columns include:

```text
source_file, subject, paper, year, session, variant, doc_type, page, text
```

Consumers must filter `doc_type` explicitly; a file is not guaranteed to contain only question-paper pages.

### 6.2 Questions CSV

`data/extracted/<subject>_questions.csv` retains the original top-level fields and adds structure. The current contract includes:

```text
subject, paper, year, session, variant, doc_type,
question_number, question_text, marks, subquestions, total_marks
```

`subquestions` is JSON-encoded. Each structured item carries its label/text and mark information as produced by `segment_questions.py`. `total_marks` is the sum of parsed sub-question marks, or the top-level mark when there is no sub-label. Unlabeled marks remain traceable through raw question text and the top-level mark field.

Downstream code must preserve unknown/additive columns so later schema growth does not break existing consumers.

### 6.3 Pair CSV

`data/extracted/<subject>_qp_ms_pairs.csv` has one row per matched metadata key:

```text
subject, paper, year, session, variant, qp_text, ms_text
```

The current phase deliberately stores full documents side by side. It does not claim that each mark-scheme point is aligned to a particular question.

### 6.4 Tagged CSV

`data/extracted/<subject>_tagged_questions.csv` extends question rows with model-derived fields such as:

```text
topic, subtopic, command_word, difficulty, marking_points
```

The future reviewed-content contract should additionally carry curriculum mapping metadata, for example `curriculum_stage`, `grade_band`, `chapter_id`, `chapter_name`, `syllabus_revision`, `review_status`, and `tag_model_version`. These fields are needed before recommendations can reliably target a student’s weak chapter.

The exact JSON encoding must be treated as an artifact contract and validated before database ingestion. A missing or malformed response must not be silently converted into a confident tag.

## 7. CLI contract

The supported dispatcher is `python -m src.cli`; the package also exposes a `past-paper-ai` console script through `pyproject.toml`.

| Command | Purpose | Key option |
|---|---|---|
| `validate` | validate configured subjects and raw PDF filenames | `--subject` |
| `extract` | extract page text from PDFs | `--subject`, `--mock` |
| `segment` | segment questions/subquestions and marks | `--subject`, `--mock` |
| `match` | pair QP and MS documents | `--subject` |
| `analyze` | summarize question distributions | `--subject` |
| `build-prompt` | create a practice-paper prompt | `--subject` |
| `generate` | generate a paper using the existing Gemini workflow | subject/options defined by implementation |
| `tag` | batch-tag questions and mark schemes | `--subject`, `--limit`, `--dry-run` |
| `ingest` | migrate/load tagged data into the database | `--subject`, database options |
| `run` | existing convenience sequence | subject/options defined by implementation |

The current `run` convenience command executes the original local sequence (extract, segment, analyze, build-prompt). It does not automatically run match, tag, generate, or ingest. This separation is intentional while manual quality gates exist.

## 8. Gemini integration requirements

- Load `GEMINI_API_KEY` with `python-dotenv`.
- Use a bounded batch process, never an unbounded request loop.
- Expose `--limit` for controlled samples and `--dry-run` to print prompts without API calls.
- Delay between calls to reduce rate-limit pressure.
- Parse JSON defensively; retry malformed/non-JSON responses once.
- Log a warning and skip the individual record after the retry fails.
- Keep the source question/mark-scheme text separate from the instruction that governs output.
- Treat extracted text as untrusted content because it may contain instruction-like text.
- Preserve the raw source and model response context needed for review, subject to privacy and copyright policy.

## 9. Database requirements

SQLAlchemy models in `src/db/models.py` represent:

- `subjects`
- `questions`
- `mark_scheme_points`
- `users`
- `attempts`
- `mastery`
- `papers`
- `paper_questions`

The current schema is a foundation, not yet the complete personalization model. A future application layer must add or formalize curriculum chapters, student diagnostic evidence, chapter-level mastery, recommendation reasons, and school/class scope.

Alembic migration `0001_initial_schema` creates the initial schema. The application must use `DATABASE_URL`; local SQLite is useful for tests, while PostgreSQL is the target for JSONB and production behavior.

Ingestion must upsert by the question natural key:

```text
subject + paper + year + session + variant + question_number + sub_label
```

Mark-scheme points must likewise have a stable parent question and duplicate protection.

## 10. Testing requirements

Tests should cover:

- valid and invalid filename parsing;
- session normalization;
- subject-plan validation;
- extraction mock behavior;
- single-part, multi-part, nested, and unlabeled-mark segmentation;
- QP/MS matching and variant mismatch warnings;
- malformed Gemini response retry/skip behavior without requiring a live API;
- database migration and idempotent ingestion against a temporary database;
- source-to-database field mapping.

Live Gemini calls, real PDFs, and production Postgres should be separate integration/manual checks, not prerequisites for deterministic unit tests.

## 11. Error and logging requirements

Errors should identify:

- subject and source filename;
- phase and operation;
- page or question number where available;
- whether processing skipped one record or aborted the batch;
- the output path written, if a partial artifact exists.

Warnings are appropriate for missing QP/MS counterparts, skipped malformed model responses, and uncertain data. Fatal errors are appropriate for invalid configuration, missing required input, inability to write an output, or an unavailable required database.

## 12. Current technical gaps

- There is no API boundary or request validation layer yet.
- There is no frontend or client-side state model.
- There is no production Postgres connection verification in this workspace.
- Tagged output is currently blocked in real mode when `GEMINI_API_KEY` is absent; the dry-run path is available.
- The current sample page data contains QP rows but no MS rows, so the pair output has no matched records yet.
- Question-to-mark-scheme alignment is still document-level.
- Tag normalization, confidence, reviewer approval, source revision, and model/version metadata are not yet first-class columns.
- `SUBJECT_PAPER_MARKS` in `src/segment_questions.py` duplicates configuration and should eventually be removed or derived from the subject plan.
- The current data model has topic/subtopic fields but no approved school chapter catalog, grade/stage mapping, diagnostic evidence, confidence, recommendation reason, or class scope.
- The configured subject list is not yet a complete Grade 8–12 curriculum map for the target school.
- A generic “practice by topic” filter is insufficient for the product’s main promise; chapter-level mapping and weakness evidence are required.
- Production backups, migrations in CI, secrets management, telemetry, rate limiting, and RLS are not implemented.

## 13. Engineering decision principles

1. Keep raw inputs and intermediate artifacts reproducible.
2. Prefer additive schema changes over breaking existing CSV consumers.
3. Make natural keys explicit before adding caching or upserts.
4. Keep batch AI enrichment offline and reviewable.
5. Stop at phase gates when quality evidence is missing.
6. Trace defects backward from final output to source extraction and filename metadata.

## 14. Personalization architecture requirement

The first application architecture must support this data flow:

```text
school curriculum map
        ↓
Cambridge content mapped to grade/stage + chapter
        ↓
diagnostic evidence and attempts
        ↓
subject/chapter weakness profile with confidence
        ↓
explainable recommendation
        ↓
targeted practice and updated evidence
```

The recommendation service should return the target chapter, evidence summary, confidence/insufficient-evidence state, selected activity, and expected marks/time. It must not return only a generic “try this question” result.
