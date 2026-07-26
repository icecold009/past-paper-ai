# Application Flow and Navigation

## 1. Status and scope

This document maps the flows that exist in the repository and the navigation planned for the future student application.

- Reviewed against repository: 2026-07-26
- Current user interface: command line only
- Future interface: web application backed by an API
- No frontend routes, FastAPI routes, authentication screens, or deployed navigation exist yet

The offline operator flow is implemented in phases. The student navigation below is a target flow and must not be mistaken for shipped functionality.

## 2. Offline data flow

```text
Configure subject plan
        ↓
Validate source filenames
        ↓
Extract one row per PDF page
        ↓
Segment top-level questions, subquestions, and marks
        ├──────────────► Analyze distributions
        │                         ↓
        │                  Build generation prompt
        │                         ↓
        │                  Generate practice paper
        ↓
Match QP with MS by metadata
        ↓
Batch-tag question units and extract marking points
        ↓
Human review gate
        ↓
Ingest reviewed data into relational database
```

The fork after segmentation is useful: analysis and prompt construction can be inspected independently of Gemini tagging, while matching/tagging are gated by source quality.

## 3. Current CLI/operator flow

### 3.1 Validate

Command:

```powershell
python -m src.cli validate --subject 9618
```

The operator uses this before extraction to confirm that filenames can be parsed and belong to the configured subject/paper plan. A validation failure should be fixed at the source-file or configuration level before later phases run.

### 3.2 Extract

```powershell
python -m src.cli extract --subject 9618
```

The operator receives page-level CSV output under `data/extracted/`. Both QP and MS documents may occupy the same subject page CSV, so later commands must use `doc_type`.

### 3.3 Segment

```powershell
python -m src.cli segment --subject 9618
python -m src.cli segment --mock
```

The operator reviews question rows, `subquestions`, `marks`, and `total_marks`. This is the first important structure gate: if boundaries or marks are wrong, later tags and database rows are wrong too.

### 3.4 Match

```powershell
python -m src.cli match --subject 9618
```

The command pairs full QP and MS text by subject, paper, year, session, and variant. It reports missing counterparts. It does not align individual questions to mark-scheme points.

### 3.5 Tag

Dry-run first:

```powershell
python -m src.cli tag --subject 9618 --limit 10 --dry-run
```

Then run a bounded real sample only after the prompt is reviewed:

```powershell
python -m src.cli tag --subject 9618 --limit 10
```

At least 15–20 tagged questions should be compared by hand with the actual syllabus before full-dataset tagging. A missing API key or malformed response is a controlled stop/skip condition, not a reason to fabricate data.

### 3.6 Analyze, build, and generate

```powershell
python -m src.cli analyze --subject 9618
python -m src.cli build-prompt --subject 9618
python -m src.cli generate --subject 9618
```

These commands consume earlier artifacts and should be run only after their input phase has passed review.

### 3.7 Ingest

```powershell
alembic upgrade head
python -m src.cli ingest --subject 9618
```

Ingestion loads tagged questions and available marking points and is safe to rerun because it uses natural-key upsert behavior. A local SQLite database can verify the workflow; production target behavior is PostgreSQL.

## 4. Operator review flow

The reviewer should inspect artifacts in this order:

1. Source filename and subject-plan validity.
2. Page text for representative source files.
3. Top-level question boundaries.
4. Nested sub-question labels and marks.
5. QP/MS match coverage, especially variants.
6. Gemini prompts in dry-run output.
7. At least 15–20 real tags against syllabus knowledge.
8. Mark-scheme point extraction against the source MS.
9. Analysis and generated prompt distributions.
10. Database counts and duplicate checks.

If an output is wrong, trace backward to the earliest incorrect artifact. Do not correct only the final CSV by hand and leave the pipeline source inconsistent.

## 5. Future student navigation

### 5.1 Primary navigation

The future web application should use a small, stable navigation model:

- Dashboard
- Practise
- Papers
- Progress
- Settings

On smaller screens, Dashboard, Practise, and Progress should remain directly reachable; secondary items can be placed in a menu.

### 5.2 Proposed routes

These are proposed routes, not current files:

```text
/                         landing or authenticated redirect
/login                    sign in
/dashboard                current progress and continue action
/practice                 choose subject, paper, mode, filters
/practice/new             configure a session
/practice/:sessionId      answer questions
/practice/:sessionId/review review submitted answers and feedback
/papers                    browse source/generated papers
/papers/:paperId           paper detail and start action
/progress                  mastery by topic/subtopic/command word
/settings                  profile, preferences, privacy, export/delete
```

### 5.3 Student flow: start a practice session

```text
Dashboard
   ↓
Practise
   ↓
Choose subject and paper scope
   ↓
Choose mode: targeted / mixed / timed
   ↓
Choose filters: topic, subtopic, command word, difficulty, marks, duration
   ↓
Preview question count and marks budget
   ↓
Start session
```

The preview must disclose when filters cannot be satisfied and should not silently substitute unrelated questions.

### 5.4 Student flow: answer and submit

```text
Question view
   ↓
Enter answer
   ↓
Save draft or submit answer
   ↓
Confirm submission if needed
   ↓
Record attempt
   ↓
Show marks and feedback
   ↓
Next question or session review
```

The answer screen must show question number, sub-label when present, marks possible, progress, and save/submission state. A submitted answer should become immutable unless the product explicitly supports an edit-and-resubmit event.

### 5.5 Student flow: review and mastery

Feedback should show:

- marks earned and possible;
- marking points met, partially met, or missed where supported;
- a concise explanation;
- topic/subtopic and command word;
- an action such as retry, view related practice, or return to progress.

Progress should aggregate attempts only after the grading result is valid. A model-generated tag that is pending human review should not silently drive a high-confidence mastery recommendation.

## 6. Screen requirements

### Dashboard

- Continue the most recent incomplete session.
- Show recent score trend and weak areas.
- Show data freshness or review status if source content is newly imported.
- Keep the primary action “Start practice” visually obvious.

### Practice setup

- Subject and paper are required.
- Filters use only available values.
- Show selected marks/questions/time estimate.
- Explain whether the session is generated or source-based.
- Make reset and start actions distinct.

### Practice question

- Render structured subquestions in order.
- Preserve marks beside the relevant unit.
- Provide keyboard-accessible answer input.
- Show autosave state without implying submission.
- Make next/submit actions predictable.

### Feedback

- Never conflate marks possible with marks earned.
- Distinguish source mark-scheme evidence from AI explanation.
- Provide a report/correction action for suspected bad data.

### Progress

- Topic and subtopic views must identify data volume.
- Avoid implying mastery from too few attempts.
- Let users inspect the questions contributing to a score.

## 7. State and error flows

The future app must explicitly model:

- loading subject/question metadata;
- no questions matching selected filters;
- source question lacking a mark scheme;
- tag pending review;
- autosave failure;
- expired or invalid session;
- answer-grading failure;
- network interruption during submission;
- deleted or unavailable source paper;
- permission denied for another user’s paper or attempt.

Errors should preserve user-entered answer text locally where safe, provide a retry action, and avoid duplicate submissions through idempotency keys.

## 8. Permission flow

Unauthenticated visitors may eventually see public product information and possibly approved sample questions. User data, attempts, papers, mastery, and settings require authentication. Ownership must be checked server-side for every ID-based resource; hiding a link is not authorization.

## 9. Deep links and recovery

- A paper/session URL should reopen the appropriate state after sign-in.
- A stale session should explain what happened and offer a safe restart.
- A browser refresh must not submit an answer twice.
- A user returning after interruption should see the last durable save and its timestamp.
- A deleted question should leave an auditable historical reference in attempts rather than breaking the entire progress view.

## 10. Current versus planned flow

| Flow | Status |
|---|---|
| Validate, extract, segment, analyze, build prompt via CLI | Implemented |
| Match QP/MS via CLI | Implemented; current sample lacks MS rows |
| Gemini dry-run/limited tag flow | Implemented; real run requires API key and manual review |
| Alembic migration and idempotent ingestion | Implemented; SQLite verified, Postgres deployment pending |
| Student login and dashboard | Planned |
| Practice session and answer persistence | Planned |
| Mark-scheme-aware grading | Planned/partially scaffolded by schema |
| Mastery recommendations | Planned |
