# Implementation Plan

## 1. Delivery rules

This project is intentionally phased. Each phase assumes the previous phase is merged and working, and each phase ends with a manual or automated gate. Do not batch later phases into the same session when a manual review is explicitly required.

The product north star for every phase is the target school’s Cambridge Grades 8–12 learner: identify a student’s weak subjects/chapters, explain the evidence, and deliver useful targeted help. A feature that adds generic AI chat without improving this loop is outside the main product direction.

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
| 5 | School curriculum map and personalization model | Foundation in progress | Versioned chapter/mapping entities, deterministic evidence states, and a reviewed-map importer exist; school-approved content remains required |
| 6 | FastAPI read/write service | v1 implemented | Subjects, questions, attempts, mastery, curriculum, guidance, diagnostics, and retry-safe practice-session contracts are covered; provider auth/RLS remains |
| 7 | Authentication, school permissions, and RLS | Foundation in progress | Signed request verification and ownership/school checks exist; identity-provider integration and database RLS remain |
| 8 | Student web frontend | v1 slice implemented | Subject picker, mastery dashboard, question answering, and grading feedback work against the FastAPI service; full diagnosis flow, auth, persistence, and visual QA remain |
| 9 | Weak-spot paper generation | v1 slice implemented | Weakest-cell selection, unseen real-question weighting, labeled Gemini fallback questions, paper persistence, and frontend display; auth and full paper-taking flow remain |
| 10 | Practice sessions and answer persistence | Foundation in progress | Retry-safe diagnostic/practice records and state transitions exist; full paper-taking and grading attachment remain |
| 11 | Mark-scheme-aware grading and feedback | v1 slice implemented | Existing attempt grading preserves mark-scheme evidence; policy, human evaluation, corrections, and version metadata remain |
| 12 | Mastery, weakness profiles, and recommendations | Foundation in progress | Transparent chapter evidence and explainable recommendations exist; approved mappings, evaluation, and cold-start rollout remain |
| B | Adaptive study engine revamp | In progress | Normalized content packs, optional source providers, personalized guidance, and student-first runtime flow |
| 13 | Production deployment and operations | Planned | Requires security, backups, monitoring, and recovery drills |

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

## 7. Phase 5 — school curriculum and personalization model

### Objective

Define the school-specific learning map that turns raw Cambridge subject/topic data into the chapter-level targets used by recommendations.

### Required work

1. Confirm the Cambridge stages and Grade 8–12 subjects taught at the target school.
2. Create an approved chapter catalog for each subject, including sequence and syllabus revision.
3. Map reviewed questions/topics to one or more chapters.
4. Define baseline/diagnostic evidence and evidence thresholds.
5. Define student states such as `not_enough_evidence`, `developing`, `needs_practice`, and `strong`.
6. Define explainable recommendation reasons and student override/dismissal behavior.
7. Add schema/API contracts for curriculum chapters, evidence, recommendations, and school/class scope.

### Gate

A teacher or subject expert can inspect a sample of mappings and understand why a student would receive a chapter recommendation. No full-dataset recommendation rollout proceeds while the school chapter map is undefined.

## 8. Phase 6 — API service

### Proposed sequence

1. Add FastAPI application package without changing batch modules.
2. Add health/readiness endpoints.
3. Add read-only subject, paper, question, and filter endpoints.
4. Add request/response schemas and pagination.
5. Add structured error responses and request IDs.
6. Add authenticated paper/session endpoints only after school permissions and RLS requirements are ready.
7. Add integration tests against a disposable database.

### Gate

No endpoint may expose another user’s attempts, papers, mastery, or answer text in negative authorization tests.

## 9. Phase 7 — auth, school permissions, and RLS

### Required work

- Select an identity provider.
- Define session/token handling and logout/revocation.
- Establish user ownership rules.
- Add database policies or a server-side equivalent.
- Test anonymous, same-user, and cross-user access for every resource.
- Define admin/teacher/content-reviewer privileges separately from student privileges.
- Define school/class scope and ensure individual weakness profiles are private.

### Gate

Cross-user reads and writes fail even when a user guesses a valid resource ID.

## 10. Phase 8 — frontend

### Sequence

1. Implement design tokens and accessible app shell.
2. Build login, Grade 8–12 onboarding, and session state.
3. Build the diagnostic/baseline flow.
4. Build the weakness dashboard and chapter view.
5. Build recommended targeted practice and question/answer screen.
6. Build feedback and progress by subject/chapter.
7. Add issue-reporting and empty/error states.
8. Run responsive and accessibility QA.

Do not build visual polish ahead of the question/marks/feedback data contract.

## 11. Phase 9 — practice and answer persistence

- Define a paper/session state machine: draft, active, submitted, reviewed, abandoned/expired.
- Make answer submission idempotent.
- Snapshot marks possible at submission.
- Define the relationship between targeted chapter activities and exam-paper sessions.
- Keep recommendation context attached to the session.

## 12. Phase 10 — mark-scheme-aware grading and feedback

- Define whether grading is automatic, human-assisted, or hybrid.
- Store grading model/version and evidence.
- Provide a correction path when source or grading is wrong.
- Show chapter impact only after grading is valid.

## 13. Phase 11 — mastery, weakness profiles, and recommendations

- Start with transparent score calculations.
- Handle insufficient attempts and cold-start users.
- Separate school chapter, topic, subtopic, and command-word dimensions.
- Store review timestamps and scheduling decisions.
- Store recommendation reason, evidence, confidence, and rule/model version.
- Evaluate recommendations against actual improvement rather than click-through alone.

## 14. Phase 12 — production operations

- Deploy API, worker/batch process, database, and frontend as separately observable components.
- Add secret management and least-privilege service accounts.
- Add migrations in deployment pipeline.
- Add error tracking, metrics, logs, health checks, backups, and restore tests.
- Load test question browsing, practice sessions, and submission paths.
- Define rollback and incident procedures.

## 15. Full-dataset release gate

Before processing the full corpus:

1. Confirm source PDF inventory and filename validation.
2. Confirm the school’s Cambridge Grade 8–12 stages, subjects, chapters, and syllabus revisions.
3. Confirm QP and MS coverage by subject/paper/session/variant.
4. Run extraction and segmentation on representative real papers.
5. Review marks and nested structure.
6. Dry-run Gemini prompts.
7. Run a bounded real sample.
8. Review at least 15–20 tagged questions against the syllabus.
9. Review mark-scheme points against source text.
10. Review question-to-school-chapter mappings with a subject expert.
11. Record model name/version, date, prompt version, and curriculum-map version.
12. Run full tagging with bounded retries and rate limits.
13. Inspect skip/error counts.
14. Run analysis and compare distributions with expected paper structure.
15. Ingest into a disposable database.
16. Verify counts, duplicates, missing sources, mark totals, and chapter coverage.
17. Archive a manifest of inputs, outputs, code revision, and configuration.

## 16. Testing matrix

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

## 17. Branch, commit, and handoff protocol

- Create a feature branch before implementation.
- Keep one phase or tightly scoped documentation change per branch/commit series.
- Run relevant tests and `git diff --check` before committing.
- Commit with a message that describes the actual scope.
- Push the feature branch for review.
- Do not merge to `main` without explicit approval.
- Handoff must include changed files, verification commands, known gaps, and the next manual gate.
