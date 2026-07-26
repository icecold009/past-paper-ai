# Project Backlog

## 1. Purpose and status

- Project: Past Paper AI
- Reviewed against repository: 2026-07-26
- Backlog status: current incomplete work and decisions
- Product north star: help Cambridge Grades 8–12 students at the target school identify weak subjects and chapters, understand why they need attention, and complete targeted activities that improve them

This backlog records work that is not complete. It is intentionally separate from the implementation plan: the implementation plan describes the phase sequence, while this document is the working list of unfinished tasks, blockers, acceptance criteria, and decisions.

The product should remain distinct from a generic AI website. A backlog item is valuable when it improves the Cambridge curriculum → student evidence → chapter recommendation → targeted help → improvement loop.

## 2. Status legend

- `BLOCKED`: cannot safely proceed until a named external input or prerequisite is available.
- `READY`: can be started with the current repository and known requirements.
- `IN PROGRESS`: work has started but the acceptance criteria are not complete.
- `PLANNED`: agreed future work that depends on earlier phases.
- `DECISION`: requires a product, school, curriculum, or policy decision before implementation.

Priority:

- `P0`: release blocker or prerequisite for trustworthy data/product behavior.
- `P1`: required for the first useful personalized student experience.
- `P2`: important follow-up, scale, polish, or operational maturity.

## 3. Current state snapshot

### Complete enough to move forward

- Phase 1 segmentation code and tests exist for top-level questions, subquestions, nested labels, and marks.
- Phase 2 QP/MS matching code and tests exist.
- Phase 3 Gemini tagging module supports bounded runs, dry-run, delay, retry, and skip behavior.
- Phase 4 SQLAlchemy models, Alembic migration, and idempotent ingestion exist.
- Local SQLite migration and repeated ingestion have been verified.
- Seven core product/design/security documents exist and reflect the personalized Cambridge learning direction.

### Still incomplete

- The target school’s actual Cambridge Grades 8–12 stage, subject, syllabus, and chapter map is not in the repository.
- The current sample data contains QP rows but no MS rows, so real QP/MS coverage has not been demonstrated.
- Real Gemini tagging is blocked until `GEMINI_API_KEY` is configured.
- The required 15–20-question manual syllabus review has not been completed.
- The current database does not yet model curriculum chapters, diagnostic evidence, recommendation reasons, or school/class scope.
- There is no FastAPI service, frontend, authentication, RLS, teacher workflow, or production deployment.

## 4. P0 — trust and prerequisite blockers

### BL-001 — Confirm the school curriculum scope

- Status: `DECISION`
- Priority: `P0`
- Dependency: school/subject-owner input
- Owner: product owner + subject teachers

Confirm:

- Cambridge stage(s) represented by Grades 8–12 at the school;
- subjects to support first;
- syllabus/exam-board variants and revision years;
- exact school grade-to-stage mapping;
- chapter list and chapter order for every first-release subject;
- whether the school uses custom chapter names that differ from Cambridge syllabus headings.

Acceptance criteria:

- An approved versioned curriculum map exists outside model prompts.
- Every supported student grade has an explicit subject/chapter scope.
- The map identifies content that is available for diagnosis, targeted practice, exam practice, or teacher review.

### BL-002 — Build the school curriculum/chapter map

- Status: `PLANNED`
- Priority: `P0`
- Dependency: BL-001
- Related phases: Phase 5

Create the data structure and reviewed mappings for:

```text
grade/stage + subject + syllabus revision + chapter
        ↕
source question/topic/subtopic/paper
```

Acceptance criteria:

- Each release question can be mapped to one or more approved chapters or marked unmapped.
- Mappings have review status, confidence, version, and reviewer/date where applicable.
- A chapter name is not accepted solely because Gemini invented a plausible label.
- Mapping coverage and unmapped counts can be reported before student recommendations are enabled.

### BL-003 — Obtain representative real QP and MS data

- Status: `BLOCKED`
- Priority: `P0`
- Dependency: source PDF inventory
- Related phases: Phases 1–2

Add representative valid question papers and matching mark schemes for the first supported subjects, grades/stages, sessions, and variants. Confirm that the combined pages CSV actually contains both `doc_type == "qp"` and `doc_type == "ms"` rows.

Acceptance criteria:

- Filename validation passes for the intended corpus.
- Each selected QP has the expected matching MS or a documented reason it is unavailable.
- Variant mismatches do not pair.
- Full QP/MS text order is manually checked for at least one pair per first-release subject.

### BL-004 — Complete Phase 3 Gemini setup and bounded sample

- Status: `BLOCKED`
- Priority: `P0`
- Dependency: `GEMINI_API_KEY` and representative matched data
- Related phases: Phase 3

Run the tagger in the required order:

```powershell
python -m src.cli tag --subject <subject> --limit 10 --dry-run
python -m src.cli tag --subject <subject> --limit 10
```

Acceptance criteria:

- Dry-run prompts are reviewed before API calls.
- The real sample completes without exposing the API key in output.
- Malformed responses retry once, then skip with a warning.
- Topic, subtopic, command word, difficulty, and marking-point JSON are structurally valid.
- Skip/error counts are recorded.

### BL-005 — Perform the mandatory 15–20 tag review

- Status: `BLOCKED`
- Priority: `P0`
- Dependency: BL-004
- Related phases: Phase 3 manual gate

Review at least 15–20 tagged questions by hand against the actual Cambridge syllabus, including multi-part questions, unusual wording, different command words, difficulty levels, and mark-scheme points.

Record:

- question/source identifier;
- predicted tag;
- reviewer assessment;
- correction;
- error category;
- whether the issue is prompt, source extraction, taxonomy, or model behavior.

Acceptance criteria:

- Review notes exist and are reproducible.
- Recurring errors are fixed or explicitly accepted.
- No full-dataset tagging proceeds while tags are plausible but syllabus-inaccurate.

### BL-006 — Validate segmentation and marks on real papers

- Status: `READY`
- Priority: `P0`
- Dependency: BL-003
- Related phases: Phase 1 manual gate

Inspect real outputs for:

- top-level question boundaries;
- `(a)`, `(b)`, `(i)`, `(ii)`, and nested labels;
- unlabeled marks;
- `subquestions` JSON;
- `total_marks` reconciliation;
- page breaks and multi-page questions.

Acceptance criteria:

- A representative sample is signed off by a reviewer.
- Defects are fixed in segmentation code and regression tests, not hand-edited in CSVs.

### BL-007 — Validate database ingestion against PostgreSQL

- Status: `READY`
- Priority: `P0`
- Dependency: BL-003 and a disposable PostgreSQL instance
- Related phases: Phase 4

Repeat the local SQLite migration/ingestion check against PostgreSQL.

Acceptance criteria:

- `alembic upgrade head` succeeds on a disposable database.
- Ingesting the same source twice produces no duplicate questions or points.
- Counts by subject, paper, chapter-ready content, and mark-scheme points are explainable.
- JSONB behavior in `attempts.points_awarded` is verified.
- Connection secrets are supplied through `.env`, never committed.

## 5. P1 — personalized learning foundation

### BL-101 — Define diagnostic design

- Status: `DECISION`
- Priority: `P1`
- Dependency: BL-001 and BL-002

Decide how the first weakness profile is created:

- short baseline by subject/chapter;
- existing marked attempts;
- teacher-entered evidence;
- student confidence/self-report;
- a labeled combination of these signals.

Define:

- diagnostic length and time;
- chapter coverage;
- evidence thresholds;
- treatment of skipped questions;
- confidence and “not enough evidence” behavior;
- how often the diagnostic can be repeated;
- whether the student can disagree with a result.

Acceptance criteria:

- A student cannot be marked weak from one accidental error.
- The output contains chapter, evidence count, confidence, and next-step state.
- The process is age-appropriate for Grades 8–12.

### BL-102 — Add curriculum and diagnostic database entities

- Status: `PLANNED`
- Priority: `P1`
- Dependency: BL-002 and BL-101
- Related files: `src/db/models.py`, Alembic migrations, `src/db/ingest.py`

Add or formalize:

- `curriculum_chapters`;
- reviewed question-to-chapter mappings;
- diagnostic evidence;
- chapter-level mastery/strength state;
- recommendation records and reason/version;
- school/class membership if teacher features are in the first release.

Acceptance criteria:

- Historical attempts retain the curriculum context used at the time.
- A recommendation can be reproduced from stored evidence and a versioned rule/model.
- Database uniqueness, foreign keys, and migration rollback/forward-fix behavior are tested.

### BL-103 — Implement an explainable first recommendation engine

- Status: `PLANNED`
- Priority: `P1`
- Dependency: BL-101 and BL-102

Start with deterministic rules rather than opaque runtime model calls. The service should return:

```json
{
  "chapter_id": "...",
  "state": "needs_practice",
  "reason": "Two recent marked attempts were below the target range",
  "evidence_count": 2,
  "confidence": 0.78,
  "activity_type": "targeted_practice"
}
```

Acceptance criteria:

- The recommendation is limited to the student’s Grade 8–12 curriculum scope.
- The student sees why it was selected.
- The system can return `not_enough_evidence`.
- A student can dismiss or request a different activity without corrupting the profile.
- Recommendation quality is evaluated by chapter improvement, not click-through alone.

### BL-104 — Create the first API contract

- Status: `PLANNED`
- Priority: `P1`
- Dependency: BL-102 and BL-103

Define FastAPI endpoints and schemas for:

- school/grade/stage context;
- subjects and chapters;
- diagnostic start/save/submit;
- weakness profile;
- recommendation retrieval and dismissal;
- question/practice session creation;
- answer save/submit and feedback;
- progress and evidence history.

Acceptance criteria:

- Request/response schemas are versioned and validated.
- Pagination/filter limits are defined.
- Errors are safe and actionable.
- State-changing operations are idempotent where retries are possible.

### BL-105 — Implement authentication, school roles, and RLS

- Status: `PLANNED`
- Priority: `P1`
- Dependency: BL-104 and school policy decisions

Implement student, teacher/reviewer, and school-admin access with server-side ownership checks and database isolation.

Acceptance criteria:

- Students see only their own diagnostics, attempts, weakness profiles, papers, and mastery.
- Teachers see only authorized class aggregates or approved individual data.
- Classmates cannot discover another student’s weakness profile.
- Direct object-reference and cross-tenant negative tests pass.
- RLS or an equivalent control is enabled before multi-user release.

### BL-106 — Build the student MVP frontend

- Status: `PLANNED`
- Priority: `P1`
- Dependency: BL-104 and BL-105

Build in this order:

1. onboarding: Grade 8–12/Cambridge stage, subjects, and school context;
2. diagnostic/baseline;
3. dashboard with supported weak subjects/chapters;
4. explainable chapter view;
5. targeted help/practice;
6. question answering and feedback;
7. progress and next recommendation.

Acceptance criteria:

- The main action is “work on this chapter,” not “ask the AI anything.”
- Empty, loading, error, insufficient-evidence, and pending-review states exist.
- The UI never calls a student permanently weak.
- Keyboard, responsive, contrast, zoom, and screen-reader checks pass.

### BL-107 — Define and implement grading/feedback policy

- Status: `PLANNED`
- Priority: `P1`
- Dependency: BL-003, BL-005, BL-104

Decide whether feedback is automatic, teacher-reviewed, or hybrid. Define mark-scheme point matching, partial credit, uncertainty, appeal/correction, and model/version display.

Acceptance criteria:

- Marks earned and marks possible are always distinct.
- Missing mark schemes do not produce fabricated feedback.
- The student can report incorrect question structure, marks, tags, or feedback.
- Grading results retain evidence and version metadata.

## 6. P2 — school product and platform maturity

### BL-201 — Teacher class dashboard

- Status: `PLANNED`
- Priority: `P2`
- Dependency: BL-105 and sufficient student data

Provide privacy-preserving aggregates:

- chapter coverage;
- class-level areas needing support;
- participation and completion;
- improvement over time.

Do not expose public student rankings or individual weaknesses by default.

### BL-202 — Generated practice papers constrained by weakness

- Status: `PLANNED`
- Priority: `P2`
- Dependency: BL-002, BL-005, BL-103, BL-107

Extend paper generation so a generated paper can target selected chapters, marks, difficulty, command words, time, grade/stage, and syllabus revision while preserving source provenance.

### BL-203 — Content review workflow

- Status: `PLANNED`
- Priority: `P2`
- Dependency: BL-005 and BL-102

Create reviewer tools for question structure, marks, chapter mappings, tags, marking points, corrections, and review history.

### BL-204 — Source and curriculum versioning

- Status: `PLANNED`
- Priority: `P2`
- Dependency: BL-002 and BL-102

Version source papers, syllabus revisions, chapter maps, prompts, model versions, tags, and corrections so old attempts remain interpretable.

### BL-205 — Production operations

- Status: `PLANNED`
- Priority: `P2`
- Dependency: BL-105 and deployment decision

Add:

- managed secrets;
- CI dependency and secret scanning;
- migration checks;
- structured logs and error tracking;
- rate limits;
- backups and restore drills;
- health/readiness checks;
- monitoring and alerts;
- deployment rollback procedures;
- resource limits for PDF/Gemini batch jobs.

### BL-206 — Copyright and school data policy

- Status: `DECISION`
- Priority: `P2`
- Dependency: school and policy-owner review

Document permitted use, storage, access, retention, deletion, and sharing rules for CAIE PDFs, extracted content, mark schemes, student answers, diagnostic data, and teacher reports.

## 7. Decisions needed from the product owner/school

These decisions should be answered before the corresponding implementation tasks start:

1. Which exact Cambridge stages and Grades 8–12 subjects are in the first release?
2. What are the school’s official chapter names and sequence for each subject?
3. Which syllabus revisions and academic years are supported?
4. Will students use school accounts, invite codes, or another authentication method?
5. Can teachers see individual student data, or only class aggregates?
6. What is the first diagnostic format and target duration?
7. What does “needs practice” mean mathematically for each subject/chapter?
8. Should students receive explanations before practice, after an attempt, or both?
9. Is generated-paper creation part of the first student release or a later feature?
10. What source content may be stored and shown to students under the school’s policy?
11. What retention/deletion rules apply to minor/student data and answer history?

## 8. Recommended execution order

The next work should proceed one phase at a time:

1. BL-001: confirm school curriculum scope.
2. BL-003 and BL-006: validate representative real QP/MS data and segmentation.
3. BL-004 and BL-005: complete bounded Gemini tagging and the mandatory manual review.
4. BL-002: build and review the chapter mapping.
5. BL-007: verify PostgreSQL ingestion.
6. BL-101: define the diagnostic and weakness states.
7. BL-102 and BL-103: implement the data model and explainable recommendation rules.
8. BL-104 and BL-105: establish secure API and access boundaries.
9. BL-106 and BL-107: build the student MVP and feedback loop.
10. Start P2 work only after a real student/teacher pilot identifies the highest-value gaps.

Do not skip BL-005, BL-001, or BL-002: incorrect tags or chapter mappings would poison every personalized feature built after them.

## 9. Definition of done for backlog items

An item is complete only when:

- the implementation or decision is present in the repository or an approved project record;
- acceptance criteria are checked with evidence;
- relevant unit/integration/manual tests exist;
- known limitations are documented;
- generated artifacts are reproducible;
- security and privacy implications are reviewed;
- the result is committed on a feature branch and handed off with the next gate.

