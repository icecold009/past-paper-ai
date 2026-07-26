# Implementation Plan

## 1. Delivery rules

This project is intentionally phased. Each phase assumes the previous phase is merged and working, and each phase ends with a manual or automated gate. Do not batch later phases into the same session when a manual review is explicitly required.

The debugging philosophy is to trace backward through the pipeline:

```text
bad app output
  ← bad DB row
  ← bad tagged row
  ← bad QP/MS pair
  ← bad segmentation
  ← bad page extraction
  ← wrong filename metadata/source PDF
```

Work rules:

- Use a separate feature branch for every change set.
- Keep commits logical and reviewable.
- Do not merge to `main` without explicit approval.
- Preserve existing CSV columns when extending schemas.
- Regenerate artifacts from code rather than hand-editing final outputs.
- Stop at the phase gate when evidence is missing.

## 2. Current phase status

| Phase | Scope | Status | Gate/evidence |
|---|---|---|---|
| 1 | Extract and segment questions, subquestions, and marks | Implemented | Unit tests and mock segmentation pass; real-paper review remains important |
| 2 | Match QP/MS documents by filename metadata | Implemented | Unit test covers match and variant mismatch; current fixture has no MS rows |
| 3 | Gemini topic/command-word/difficulty tags and mark points | Code implemented | Dry-run path works; real run needs `GEMINI_API_KEY`; 15–20 hand-review gate is still required |
| 4 | SQLAlchemy schema, Alembic, idempotent ingest | Implemented | SQLite migration and two-run idempotence verified; live Postgres still pending |
| 5 | FastAPI read/write service | Planned | Define API contract, validation, ownership, and error model first |
| 6 | Authentication, permissions, and RLS | Planned | Must precede multi-user data or deployment |
| 7 | Student web frontend | Planned | Build against stable API and reviewed data |
| 8 | Practice sessions and answer persistence | Planned | Requires question selection, paper state, and idempotent submissions |
| 9 | Mark-scheme-aware grading and feedback | Planned | Requires explicit grading policy and human evaluation |
| 10 | Mastery scheduling and recommendations | Planned | Requires trustworthy attempts/tags and cold-start handling |
| 11 | Production deployment and operations | Planned | Requires security, backups, monitoring, and recovery drills |

## 3. Phase 1 — segmentation foundation

### Objective

Turn page-level extraction into question-level records with nested subquestion structure and marks.

### Implementation

- Parse top-level question starts.
- Detect alphabetic and Roman sub-labels.
- Support nested combinations such as `(a)(i)`.
- Detect `[N]` marks.
- Attach marks to the nearest sub-question or top-level question.
- Preserve existing CSV columns.
- Add JSON `subquestions` and numeric `total_marks`.

### Verification gate

- Run unit tests for single-part, multi-part, nested, and unlabeled marks.
- Run `python -m src.cli segment --mock`.
- Inspect the resulting CSV content manually.
- Test at least one real PDF layout before trusting full extraction.

### Stop conditions

- Question boundaries are shifted.
- Nested labels are flattened incorrectly.
- Total marks do not reconcile with visible mark tags.

## 4. Phase 2 — QP/MS matching

### Objective

Pair full question-paper and mark-scheme documents by the shared filename metadata key.

### Implementation

- Read the combined page-level CSV.
- Group pages by source file and `doc_type`.
- Match `(subject, paper, year, session, variant)`.
- Write full QP/MS text side by side.
- Warn for unmatched QP and unmatched MS files.

### Verification gate

- Use two matching mock filenames and one mismatched variant.
- Confirm one pair row and one warning.
- Confirm no cross-variant match.
- Inspect a real pair’s concatenated text for page-order preservation.

## 5. Phase 3 — Gemini enrichment

### Objective

Add syllabus-contextual tags and discrete mark-scheme points as a bounded offline batch.

### Implementation

- Use subject-plan name/context.
- Request strict JSON only.
- Support `--limit` and `--dry-run`.
- Rate-limit calls.
- Retry malformed/non-JSON responses once.
- Skip and warn after retry failure.
- Write a separate tagged CSV to keep source questions intact.

### Required manual gate

Before full-dataset tagging, review at least 15–20 tagged questions by hand against the actual syllabus, including multiple topics, command words, difficulty levels, nested questions, unusual wording, and mark-scheme points against the source MS.

Record corrections and recurring error patterns. Do not normalize or cluster tags until this review establishes whether the raw tag vocabulary is usable.

### Stop conditions

- API key missing or quota behavior unclear.
- Prompts encourage the model to follow source-text instructions.
- JSON is malformed at a material rate.
- Tags are plausible but syllabus-inaccurate.

## 6. Phase 4 — relational storage

### Objective

Create a durable relational layer without losing CSV reproducibility.

### Implementation

- SQLAlchemy models in `src/db/models.py`.
- Alembic initial migration.
- `.env.example` `DATABASE_URL`.
- Ingest tagged questions and mark points.
- Upsert by natural key.
- Verify with SQLite, then PostgreSQL.

### Verification gate

```powershell
alembic upgrade head
python -m src.cli ingest --subject 9618
python -m src.cli ingest --subject 9618
```

Compare counts after both runs. Query counts by subject and search for duplicate natural keys. Then repeat against a disposable PostgreSQL database before production planning.

## 7. Phase 5 — API service

### Proposed sequence

1. Add FastAPI application package without changing batch modules.
2. Add health/readiness endpoints.
3. Add read-only subject, paper, question, and filter endpoints.
4. Add request/response schemas and pagination.
5. Add structured error responses and request IDs.
6. Add authenticated paper/session endpoints only after Phase 6 requirements are ready.
7. Add integration tests against a disposable database.

### Gate

No endpoint may expose another user’s attempts, papers, mastery, or answer text in negative authorization tests.

## 8. Phase 6 — auth, permissions, and RLS

### Required work

- Select an identity provider.
- Define session/token handling and logout/revocation.
- Establish user ownership rules.
- Add database policies or a server-side equivalent.
- Test anonymous, same-user, and cross-user access for every resource.
- Define admin/teacher/content-reviewer privileges separately from student privileges.

### Gate

Cross-user reads and writes fail even when a user guesses a valid resource ID.

## 9. Phase 7 — frontend

### Sequence

1. Implement design tokens and accessible app shell.
2. Build login and session state.
3. Build subject/paper/practice setup.
4. Build question/answer screen.
5. Build feedback and progress.
6. Add issue-reporting and empty/error states.
7. Run responsive and accessibility QA.

Do not build visual polish ahead of the question/marks/feedback data contract.

## 10. Phase 8 — practice and grading

- Define a paper/session state machine: draft, active, submitted, reviewed, abandoned/expired.
- Make answer submission idempotent.
- Snapshot marks possible at submission.
- Define whether grading is automatic, human-assisted, or hybrid.
- Store grading model/version and evidence.
- Provide a correction path when source or grading is wrong.

## 11. Phase 9 — mastery

- Start with transparent score calculations.
- Handle insufficient attempts and cold-start users.
- Separate topic, subtopic, and command-word dimensions.
- Store review timestamps and scheduling decisions.
- Evaluate recommendations against actual improvement rather than click-through alone.

## 12. Phase 10 — production operations

- Deploy API, worker/batch process, database, and frontend as separately observable components.
- Add secret management and least-privilege service accounts.
- Add migrations in deployment pipeline.
- Add error tracking, metrics, logs, health checks, backups, and restore tests.
- Load test question browsing, practice sessions, and submission paths.
- Define rollback and incident procedures.

## 13. Full-dataset release gate

Before processing the full corpus:

1. Confirm source PDF inventory and filename validation.
2. Confirm QP and MS coverage by subject/paper/session/variant.
3. Run extraction and segmentation on representative real papers.
4. Review marks and nested structure.
5. Dry-run Gemini prompts.
6. Run a bounded real sample.
7. Review at least 15–20 tagged questions against the syllabus.
8. Review mark-scheme points against source text.
9. Record model name/version, date, and prompt version.
10. Run full tagging with bounded retries and rate limits.
11. Inspect skip/error counts.
12. Run analysis and compare distributions with expected paper structure.
13. Ingest into a disposable database.
14. Verify counts, duplicates, missing sources, and mark totals.
15. Archive a manifest of inputs, outputs, code revision, and configuration.

## 14. Testing matrix

| Layer | Test type | Examples |
|---|---|---|
| Parser | unit | filename/session/document type |
| Segmentation | unit | labels, nested labels, marks, edge cases |
| Matching | unit | exact match, variant mismatch, missing side |
| Tagging | unit | valid JSON, fenced JSON, retry, skip |
| Artifacts | fixture/integration | CSV columns, JSON encoding, page order |
| Database | integration | migration, upsert, FK, duplicate prevention |
| API | integration | validation, pagination, ownership |
| Frontend | component/e2e | answer save, submit, feedback, recovery |
| Security | negative | injection, cross-user access, secret leakage |
| Operations | rehearsal | restore, rollback, rate-limit behavior |

## 15. Branch, commit, and handoff protocol

- Create a feature branch before implementation.
- Keep one phase or tightly scoped documentation change per branch/commit series.
- Run relevant tests and `git diff --check` before committing.
- Commit with a message that describes the actual scope.
- Push the feature branch for review.
- Do not merge to `main` without explicit approval.
- Handoff must include changed files, verification commands, known gaps, and the next manual gate.
