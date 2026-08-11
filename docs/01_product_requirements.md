# Product Requirements Document

## 1. Document control

- Product: Past Paper AI
- Repository: `past-paper-ai`
- Scope: Cambridge Grades 8–12 school learning support, CAIE past-paper ingestion, weakness diagnosis, targeted practice, and practice-paper generation
- Status: living product baseline and target definition
- Reviewed against repository: 2026-07-26
- Primary implementation boundary today: local Python CLI and batch data pipeline

This document describes both the product that the repository is building toward and the capabilities that already exist. “Implemented” means present in the repository and verified locally. “Planned” means a product requirement or future phase; it is not available to end users yet.

## 2. Product summary

Past Paper AI is a Cambridge-focused learning platform for students in Grades 8–12 at the target school. Its purpose is to identify the subjects and chapters where each student needs help, then provide focused explanations, practice, feedback, and revision guidance.

It is deliberately different from a regular AI website. It is not a blank chatbot where a student asks arbitrary questions and receives untracked answers. It is a syllabus-aware learning loop that uses structured Cambridge content and the student’s own evidence to decide what help should come next.

The product has two connected surfaces:

1. An operator/data pipeline that validates filenames, extracts PDF text, segments questions, pairs question papers with mark schemes, adds Gemini-assisted tags and marking points, analyzes the corpus, and builds prompts for generated practice papers.
2. A future student application that establishes each learner’s curriculum context, diagnoses weak subjects and chapters, recommends the next best practice, gives mark-scheme-aware feedback, and tracks improvement over time.

The repository is currently in the first surface. It has no frontend, FastAPI application, deployed service, user authentication, or production student workflow yet.

## 3. Problem statement

CAIE papers are valuable but inconvenient to use as a personalized practice system:

- Papers are distributed as PDFs whose filenames carry important metadata but whose contents are not application-ready.
- A paper is a large document; learners need question- and sub-question-level units.
- Mark values and mark-scheme points are separate from the question text.
- A learner needs targeted help for a weak subject or chapter rather than a generic chat response or a random page of questions.
- A school needs a consistent Cambridge-aligned learning experience for Grades 8–12 without exposing one student’s answers or weaknesses to another.
- Repeated manual preparation makes it difficult to scale a consistent question bank.
- Generated practice papers are only useful if source structure, marks, syllabus context, and provenance remain traceable.

## 4. Product vision

Provide a trustworthy practice loop:

```text
CAIE source PDFs
        ↓
validated metadata and extracted text
        ↓
question/sub-question and mark-scheme units
        ↓
reviewed curriculum, topic, command-word, difficulty, and marking-point data
        ↓
student baseline and chapter weakness profile
        ↓
targeted explanation, practice, and generated papers
        ↓
feedback, attempts, mastery history, and next-step recommendations
```

Trustworthiness is a product feature. A student or reviewer should be able to understand where a question came from, how many marks it carries, which mark-scheme points support feedback, and whether AI-derived metadata has been reviewed.

## 5. Users and jobs to be done

### 5.1 Student in Grades 8–12

The student wants to:

- confirm their grade, Cambridge stage, and subjects;
- complete a short baseline or use existing attempts to identify weak subjects and chapters;
- see why a chapter has been recommended and what evidence supports it;
- practise a weak chapter at an appropriate difficulty;
- choose a subject and paper scope when they want exam-specific practice;
- practise a topic, subtopic, command word, or difficulty band;
- answer one question or a short paper under a chosen mark/time budget;
- see marks earned against marks possible;
- understand which marking points were met or missed;
- revisit weak areas and see progress over time;
- practise with generated papers that respect the selected syllabus and constraints.

### 5.2 Teacher or content reviewer

The reviewer wants to:

- inspect extracted question structure;
- verify sub-question boundaries and marks;
- review Gemini topic, subtopic, command-word, and difficulty tags against the syllabus;
- review extracted mark-scheme points;
- reject, correct, or flag low-confidence data before it is used downstream;
- compare coverage and difficulty across sessions and variants.

The teacher should be able to see class-level patterns only when the school approves that capability. Individual weakness information must not become a public leaderboard or a source of embarrassment.

### 5.3 Pipeline maintainer

The maintainer wants to:

- add a subject or paper plan without changing parsing logic;
- rerun a phase safely and reproducibly;
- identify malformed filenames, missing mark schemes, malformed model responses, and low-quality extraction;
- inspect intermediate CSVs rather than debugging only from final output;
- ingest data idempotently into the relational store;
- deploy a future API without rewriting the pipeline as application code.

## 6. Goals

### 6.1 Current goals

- Make PDF-derived question data structured at top-level and sub-question granularity.
- Make Cambridge stage, grade band, subject, chapter, and syllabus revision explicit enough to support accurate recommendations.
- Preserve filename metadata as the join key across all pipeline stages.
- Pair each question paper with its mark scheme before attempting question-to-answer alignment.
- Treat Gemini tagging as a batch, reviewable enrichment step, not a runtime dependency for every student request.
- Keep raw and intermediate artifacts inspectable.
- Provide a relational schema that can support users, attempts, mastery, and generated papers.

### 6.2 Product goals for the next application stages

- Deliver syllabus-aware practice selection for the school’s Cambridge Grades 8–12 curriculum.
- Diagnose weakness at subject and chapter level using attempts, baseline checks, confidence, recency, and available content—not one score alone.
- Make the next recommended activity explainable: the student should know which chapter it targets and why it was selected.
- Give mark-scheme-grounded feedback without presenting uncertain AI output as authoritative.
- Track learning history per user while isolating users from one another.
- Generate papers from measured coverage and difficulty constraints.
- Support reliable recovery when a batch fails, a model response is invalid, or a source file is replaced.

## 7. Non-goals for the current scope

The following are intentionally not part of the current segmentation/tagging/database phase:

- building the FastAPI service;
- building a browser frontend or mobile app;
- replacing teaching with a generic chatbot or unrestricted answer generator;
- ranking students publicly by score, weakness, speed, or AI usage;
- authentication, subscriptions, or payment;
- automatically grading arbitrary free-text answers with production guarantees;
- solving complete question-to-mark-scheme alignment for every mark point;
- hardcoding a universal topic taxonomy for every CAIE subject;
- silently accepting malformed or unreviewed Gemini output;
- deleting source PDFs or intermediate artifacts after ingestion.

## 8. Functional requirements

### FR-01: Subject and paper configuration

The system shall define supported subjects, syllabus names, papers, maximum marks, and durations in `config/subject_plan.json`. The current configured corpus is restricted to variant 2 and includes:

- 9618 — Computer Science — papers 1, 2, 3, and 4
- 9709 — Mathematics — papers 1, 3, 4, and 5
- 9231 — Further Mathematics — papers 1, 2, 3, and 4
- 9702 — Physics — papers 1, 2, 3, 4, and 5

The configuration is the source for validation and prompt context. For the student product it must eventually also represent Cambridge stage, school grade band, syllabus revision, curriculum chapter identifiers, and the mapping between the school’s chapter names and source-paper topics. Any duplicated constants in implementation code must remain synchronized or be removed in a future cleanup.

The current repository configuration contains subject/paper metadata but does not yet encode the target school’s Grade 8–12 curriculum map. That is a required product-data phase, not something the model should guess from a filename.

### FR-02: Filename validation

The system shall parse and validate filenames in the form:

```text
<subject>_<paper>_<year>_<session>_<variant>_<qp|ms>.pdf
```

The parser shall preserve subject, paper, year, session, variant, and document type. Supported session aliases are normalized to canonical values such as `MayJune`, `OctoberNovember`, and `FebruaryMarch`.

### FR-03: Page extraction

The system shall extract one row per PDF page into `<subject>_pages.csv`, preserving source filename and parsed metadata alongside page text. Extraction errors must identify the source file and page where possible.

### FR-04: Question segmentation

The system shall identify top-level question chunks and, within each chunk, detect labels such as `(a)`, `(b)`, `(i)`, `(ii)`, and nested forms such as `(a)(i)`. It shall detect mark tags such as `[2]`, `[4]`, and `[12]`.

Marks shall be attached to the nearest appropriate sub-question, or to the top-level question when no sub-label exists. The output shall retain existing columns and add structured fields including JSON-encoded `subquestions` and `total_marks`.

### FR-05: Mark-scheme pairing

The system shall pair each question paper and mark scheme by:

```text
subject + paper + year + session + variant
```

It shall output one row per matched paper pair with full question-paper text and full mark-scheme text. Missing counterparts shall produce clear warnings and shall not stop unrelated pairs from being processed.

### FR-06: Batch enrichment

For each question or sub-question, the batch tagger shall request JSON containing:

```json
{
  "topic": "...",
  "subtopic": "...",
  "command_word": "...",
  "difficulty": "easy|medium|hard"
}
```

For each matched mark scheme, it shall request a JSON object containing a short list of discrete marking points. The tagger shall support `--limit`, `--dry-run`, rate limiting, one retry for malformed responses, and warning-and-skip behavior.

### FR-07: Analysis and prompt construction

The system shall summarize question distributions and build a subject-specific practice-paper prompt from analyzed data. These outputs are downstream of segmentation and tagging and must not be treated as authoritative until source and enrichment quality have been reviewed.

### FR-08: Relational ingestion

The system shall load tagged questions and matched mark-scheme data into `subjects`, `questions`, and `mark_scheme_points`. Re-running ingestion with the same source data shall not create duplicates.

### FR-09: Future practice loop

The future application shall let an authenticated user create a paper or practice session, select questions, submit answers, receive feedback, and record an attempt. It shall store enough provenance to explain marks possible, marks earned, and the mark-scheme points used.

### FR-10: Weakness diagnosis and recommendation

The student product shall:

1. establish a learner’s grade/stage and subject context;
2. collect baseline evidence through a short diagnostic, existing attempts, teacher input, or a clearly labeled combination;
3. calculate confidence-aware weakness signals at subject and chapter level;
4. distinguish “not enough evidence” from “currently weak”;
5. recommend a next activity with a reason, expected effort, and target chapter;
6. update the recommendation after new evidence;
7. avoid recommending content outside the student’s Cambridge stage or school curriculum.

The first recommendation engine should be transparent and rule-based enough for a student or teacher to understand. Gemini may help explain or classify content, but it must not silently become the authority for a child’s learning path.

### FR-11: School and teacher context

The future product shall support the target school’s approved curriculum scope, teacher-managed class context, and age-appropriate controls. Class-level reporting must aggregate safely and must not expose individual student weaknesses to classmates.

## 9. Product quality rules

- Source metadata is more trustworthy than model-inferred metadata and must remain available.
- AI-derived fields are enrichment, not replacements for raw text.
- A missing mark scheme is a visible data-quality condition, not an invitation to invent marks.
- An unlabeled mark belongs to the most defensible parent unit and must remain inspectable in raw text.
- A model response that is not valid JSON is skipped after retry and logged; it must not corrupt the whole batch.
- Subject and paper constraints must come from configuration or validated metadata, not user prompt text alone.
- A recommendation must carry its curriculum context: grade/stage, subject, chapter, syllabus revision, and reason.
- “Weak” must be based on sufficient evidence and shown as a support signal, never as a fixed identity or public label.
- Intermediate outputs are review surfaces and should be regenerated rather than hand-edited.
- Every generated or graded artifact should retain source identifiers sufficient to trace it back to a PDF.

## 10. Future user experience acceptance criteria

The first student-facing release should satisfy at least the following:

1. A Grade 8–12 student can confirm their Cambridge stage, subjects, and school curriculum context.
2. The student can complete or skip a clearly explained baseline and understand the limits of recommendations without evidence.
3. The dashboard identifies supported weak subjects/chapters and explains the evidence and confidence behind each recommendation.
4. A student can start a focused activity for a recommended weak chapter in one or two actions.
5. A practice session displays the question text, sub-question structure, and marks possible clearly.
6. The user cannot accidentally submit an answer to the wrong question without a visible confirmation/state transition.
7. Feedback distinguishes earned marks, possible marks, and explanatory marking points.
8. Unreviewed or unavailable mark-scheme data is communicated honestly.
9. A user can leave and resume a session without losing submitted answers.
10. A user can inspect progress by subject and chapter without seeing another user’s data.
11. Keyboard navigation, focus indication, readable contrast, and responsive layouts work at the target accessibility level.

## 11. Success measures

### Data pipeline measures

- percentage of valid source PDFs accepted by filename validation;
- extraction success rate by file and page;
- percentage of top-level questions with plausible segmentation;
- percentage of questions with marks that reconcile with visible mark tags;
- question-paper/mark-scheme match rate;
- percentage of source questions mapped to an approved Cambridge grade/stage/chapter;
- malformed Gemini response rate;
- reviewer correction rate for topic, command word, and difficulty;
- percentage of ingested rows that pass natural-key uniqueness checks.

### Student product measures

- practice sessions started and completed;
- answer submission success rate;
- feedback viewed after submission;
- repeat practice in previously weak topics;
- percentage of recommendations opened and completed;
- improvement in the recommended chapter after targeted practice;
- time from diagnostic evidence to a useful next activity;
- percentage of students who can explain why an activity was recommended;
- improvement in marks or mastery score over repeated reviews;
- generated-paper usefulness rating;
- report rate for incorrect structure, marks, or feedback.

Metrics must be interpreted with quality checks. A high completion rate is not success if the underlying tags or marking points are wrong.

## 12. Major risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| PDF layout defeats regex segmentation | Incorrect question boundaries or marks | Keep raw page text, test realistic layouts, add review fixtures, and flag anomalies |
| Mark scheme does not match a QP variant | Feedback cannot be trusted | Pair by full metadata key and warn on both unmatched sides |
| Gemini makes plausible but incorrect tags | All downstream filtering degrades silently | Dry-run, limit, retry/skip, manual review of at least 15–20 records, and later confidence/review fields |
| Weakness profile is too simplistic | Students receive repetitive or discouraging recommendations | Use evidence thresholds, confidence, recency, multiple signals, and student/teacher override |
| School curriculum differs from source-paper taxonomy | Chapters appear mapped but are pedagogically wrong | Maintain an approved curriculum map and review mappings before recommendations |
| Students are labeled publicly as weak | Trust, privacy, and wellbeing harm | Private support language, access controls, no public ranking, and teacher policy |
| Prompt injection appears in extracted text | Model follows source text as instructions | Treat extracted text as untrusted data, use strict output schemas, isolate instructions, and review outputs |
| Duplicate ingestion | Incorrect counts and repeated questions | Natural-key unique constraint and upsert behavior |
| Product launches before auth/RLS | User data exposure | Require auth, ownership checks, RLS, and negative tests before multi-user deployment |
| Source licensing or redistribution restrictions | Legal/product availability risk | Define source-use policy and access controls before hosting source material |
| API cost or quota exhaustion | Batch stalls or becomes expensive | `--limit`, dry-run, delay, retry bounds, caching/idempotence, and batch observability |

## 13. Open product decisions

- Which CAIE subjects and syllabus revisions are officially supported first?
- Which Cambridge stages and Grade 8–12 subjects are taught at the target school?
- What is the school’s approved chapter list for each subject, and how does it map to CAIE syllabus/past-paper topics?
- What evidence threshold should turn a signal into a recommendation?
- Should students be able to dismiss, correct, or ask for help on a recommendation?
- May users upload their own PDFs, and if so, how are copyright and malware risks handled?
- Is the first student experience question-by-question, timed-paper, or both?
- Should feedback show exact mark-scheme wording, paraphrased points, or teacher-approved explanations?
- Which fields require human approval before they become selectable filters?
- How should partially matched or ambiguous questions appear in the UI?
- What retention period applies to answers, generated papers, and audit data?
