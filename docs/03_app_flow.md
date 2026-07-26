# Application Flow and Navigation

## 1. Status and scope

This document maps the flows that exist in the repository and the navigation planned for the future Cambridge Grades 8–12 student application.

- Reviewed against repository: 2026-07-26
- Current user interface: functional Vite frontend backed by the v1 API
- Future interface: authenticated web application backed by production services
- A v1 Vite frontend now covers subject selection, question answering, and grading feedback; authentication and deployed navigation remain planned

The offline operator flow is implemented in phases. The student navigation below mixes the shipped v1 slice with planned authenticated flows. The defining student flow is diagnosis → targeted chapter help → evidence of improvement, not open-ended AI chat.

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

The future product adds a student-facing loop after reviewed content is available:

```text
school curriculum map
        ↓
Cambridge content mapped to Grade 8–12 stage and chapter
        ↓
student baseline and attempt evidence
        ↓
subject/chapter weakness profile
        ↓
explainable next activity
        ↓
targeted practice and updated evidence
```

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

- Dashboard / My Learning
- Diagnose
- Practise
- Chapters
- Papers
- Progress
- Settings

On smaller screens, Dashboard, Practise, and Progress should remain directly reachable; secondary items can be placed in a menu.

### 5.2 Proposed routes

These are proposed routes, not current files:

```text
/                         landing or authenticated redirect
/login                    sign in
/dashboard                current weakness profile and continue action
/onboarding               grade, Cambridge stage, subjects, and school context
/diagnostic               baseline subject/chapter check
/practice                 choose a recommended chapter or exam-practice mode
/practice/new             configure a session
/practice/:sessionId      answer questions
/practice/:sessionId/review review submitted answers and feedback
/chapters                 browse school-approved chapters
/chapters/:chapterId      chapter strength, practice, and revision view
/papers                    browse source/generated papers
/papers/:paperId           paper detail and start action
/progress                  mastery by topic/subtopic/command word
/teacher/classes           teacher-only class summary, if approved by the school
/settings                  profile, preferences, privacy, export/delete
```

### 5.3 Student flow: establish a learning profile

```text
Onboarding
   ↓
Confirm Grade 8–12 / Cambridge stage / subjects
   ↓
Load the school-approved chapter map
   ↓
Complete a short baseline or import existing evidence
   ↓
Show strong, developing, weak, and not-yet-known areas
   ↓
Explain the first recommended chapter activity
```

The product must not call a student weak based on a single question. “Not enough evidence” is a valid state and should lead to a small diagnostic activity.

### 5.4 Student flow: start targeted practice

```text
Dashboard / My Learning
   ↓
Recommended weak chapter
   ↓
Why this chapter is recommended
   ↓
Choose activity: learn / practise / exam question / timed set
   ↓
Choose effort: quick 10-minute help or full practice set
   ↓
Preview target chapter, question count, marks budget, and expected time
   ↓
Start session
```

The preview must disclose when filters cannot be satisfied and should not silently substitute unrelated chapters. A student must be able to choose a different area without losing the recommendation context.

### 5.5 Student flow: answer and submit

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

### 5.6 Student flow: review and mastery

Feedback should show:

- marks earned and possible;
- marking points met, partially met, or missed where supported;
- a concise explanation;
- topic/subtopic and command word;
- target chapter and Cambridge stage;
- why the question was selected;
- an action such as retry, view related practice, or return to progress.

Progress should aggregate attempts only after the grading result is valid. A model-generated tag that is pending human review should not silently drive a high-confidence mastery recommendation. The student should see whether a chapter status is based on diagnostic evidence, marked attempts, teacher input, or insufficient evidence.

## 6. Screen requirements

### Dashboard

- Show the student’s Grade 8–12/Cambridge stage and subject context.
- Continue the most recent incomplete session.
- Show a small number of supported weak subjects/chapters, with evidence and confidence.
- Show the single clearest next action rather than an overwhelming list.
- Show data freshness or review status if source content is newly imported.
- Keep the primary action “Work on this chapter” visually obvious.

### Diagnostic

- Explain what the baseline measures and how long it will take.
- Allow a student to pause and return.
- Distinguish a diagnostic estimate from a graded exam result.
- Show chapter coverage so the student knows what has and has not been checked.

### Chapter view

- Show chapter name, Cambridge stage, subject, current status, evidence count, and last reviewed date.
- Explain the recommended next activity.
- Offer a short lesson/help action where content exists, followed by practice.
- Show related chapters only when the relationship is curriculum-approved.

### Practice setup

- Subject and paper are required.
- Grade/stage and school curriculum context are visible and cannot be silently changed by a question filter.
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

- Subject and chapter views must identify data volume and evidence type.
- Recommendations must show why an area is prioritized.
- Avoid implying mastery from too few attempts.
- Let users inspect the questions contributing to a score.

## 7. State and error flows

The future app must explicitly model:

- loading subject/question metadata;
- loading or missing the school curriculum map;
- no diagnostic evidence yet;
- insufficient evidence to call a chapter weak;
- recommendation already completed or no longer relevant;
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

Unauthenticated visitors may eventually see public product information and possibly approved sample questions. User data, diagnostic results, weakness profiles, attempts, papers, mastery, and settings require authentication. Teacher class summaries require explicit school-approved role access. Ownership must be checked server-side for every ID-based resource; hiding a link is not authorization.

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
| Vite subject picker, mastery dashboard, question screen, and feedback screen | v1 implemented; full auth, session persistence, and visual QA remain |
| Student login and dashboard | Planned |
| Grade/stage onboarding and school curriculum selection | Planned |
| Diagnostic baseline and chapter weakness profile | Planned |
| Explainable next-chapter recommendation | Planned |
| Practice session and answer persistence | Planned |
| Mark-scheme-aware grading | Planned/partially scaffolded by schema |
| Mastery recommendations | Planned |
