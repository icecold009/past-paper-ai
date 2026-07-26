# Backend Schema and Data Organization

## 1. Status

- Reviewed against repository: 2026-07-26
- Implemented: SQLAlchemy models, Alembic initial migration, database session setup, and CSV ingestion
- Locally verified: migration and idempotent ingestion against SQLite
- Target: PostgreSQL for deployed application behavior
- Not implemented yet: API endpoints, authentication provider integration, RLS policies, production backups, and user-facing grading services

The database is the future application source for reviewed question content and user learning history. CSV and JSON artifacts remain the source/interchange layer for the batch pipeline.

## 2. Entity relationship overview

```text
subjects 1 ──────── * questions 1 ──────── * mark_scheme_points
   │                    │
   │                    ├──────── * attempts * ──────── 1 users
   │                    │
   │                    └──────── * paper_questions * ─ 1 papers * ─── 1 users
   │
   └──────── * papers

users 1 ───────── * attempts
users 1 ───────── * mastery
```

`paper_questions` is the association table that preserves the selected order of questions in a generated or curated paper.

## 3. Implemented tables

### 3.1 `subjects`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | internal identifier |
| `code` | string, unique, required | CAIE syllabus code, stored as text |
| `name` | string, required | display name, e.g. Computer Science |

The natural external identity is `code`. A subject name may change for presentation; code is the stable join value.

### 3.2 `questions`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | internal identifier |
| `subject_id` | foreign key to `subjects.id` | owning syllabus |
| `paper` | string, required | paper identifier |
| `year` | integer, required | exam year |
| `session` | string, required | normalized session |
| `variant` | string, required | paper variant |
| `question_number` | string, required | top-level question number |
| `sub_label` | string, required | `(a)`, `(i)`, `(a)(i)`, or empty string for top-level |
| `topic` | string nullable | Gemini/enrichment topic |
| `subtopic` | string nullable | Gemini/enrichment subtopic |
| `command_word` | string nullable | inferred instruction verb |
| `difficulty` | string nullable | `easy`, `medium`, or `hard` |
| `marks` | integer nullable | marks assigned to this unit |
| `raw_text` | text, required | question/subquestion text |

The model has a uniqueness constraint over:

```text
subject_id + paper + year + session + variant + question_number + sub_label
```

The difficulty constraint prevents values outside the supported three-level vocabulary. Empty `sub_label` is preferred to SQL `NULL` for top-level rows because it makes the natural key deterministic across CSV reruns.

### 3.3 `mark_scheme_points`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | internal identifier |
| `question_id` | foreign key to `questions.id` | associated question unit |
| `point_text` | text, required | discrete marking point |
| `marks_value` | integer nullable | marks represented by this point when known |

The initial schema protects against duplicate points for the same question with a uniqueness constraint on `question_id + point_text`.

### 3.4 `users`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | internal user identifier |
| `email` | string, unique, required | account identity placeholder |
| `created_at` | timestamp with timezone | account creation time |

The table is schema scaffolding. Authentication and email verification are not implemented in this phase.

### 3.5 `attempts`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | attempt identifier |
| `user_id` | foreign key to `users.id` | submitting user |
| `question_id` | foreign key to `questions.id` | attempted unit |
| `submitted_answer_text` | text | submitted response |
| `points_awarded` | PostgreSQL JSONB | per-point grading detail |
| `marks_earned` | integer | awarded marks |
| `marks_possible` | integer | marks available at submission |
| `attempted_at` | timestamp with timezone | attempt time |

`points_awarded` is intentionally flexible while grading semantics are being designed. Future versions should define a versioned JSON contract rather than relying on undocumented keys.

### 3.6 `mastery`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | mastery record identifier |
| `user_id` | foreign key to `users.id` | learner |
| `topic` | string | topic dimension |
| `subtopic` | string | subtopic dimension |
| `command_word` | string | command-word dimension |
| `score` | numeric | mastery score |
| `last_reviewed_at` | timestamp with timezone | most recent contributing review |
| `next_review_at` | timestamp with timezone | scheduling hint |

The current model stores dimensions as strings to avoid prematurely locking the product into a topic taxonomy. A future normalized taxonomy may add stable topic IDs while preserving historical labels.

### 3.7 `papers`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer primary key | paper/session identifier |
| `user_id` | foreign key to `users.id` | owner/creator |
| `subject_id` | foreign key to `subjects.id` | syllabus |
| `mode` | string | targeted, mixed, timed, generated, or future mode |
| `created_at` | timestamp with timezone | creation time |

### 3.8 `paper_questions`

| Column | Type | Meaning |
|---|---|---|
| `paper_id` | foreign key to `papers.id` | selected paper |
| `question_id` | foreign key to `questions.id` | selected question |
| `position` | integer | order shown to the learner |

The composite primary key is `paper_id + question_id`; `position` preserves ordering. If the product later allows the same question more than once in a paper, this key will need to change to a surrogate row ID plus a position uniqueness rule.

## 4. Relationships and deletion behavior

The implemented model uses foreign keys and cascading relationships appropriate for source ownership:

- deleting a subject can cascade to its questions;
- deleting a question can cascade to its mark-scheme points and association rows;
- deleting a user can cascade to attempts, mastery, and owned papers;
- deleting a paper can cascade to `paper_questions`.

Before production, deletion behavior must be reviewed against retention and audit requirements. Historical attempts may need to retain a snapshot of question text, marks possible, and tag/model version rather than disappearing with mutable source content.

## 5. Source-to-database mapping

### Subjects

`config/subject_plan.json` supplies code and display name. The ingest step creates or updates the subject row.

### Questions

The tagged question CSV supplies:

```text
subject → subjects.code → subject_id
paper, year, session, variant,
question_number,
sub_label,
topic, subtopic, command_word, difficulty,
marks,
raw_text/question_text
```

The ingest step creates one top-level question row and one row per structured subquestion where the source output exposes them. Top-level rows use an empty sub-label. The exact flattening behavior must remain covered by tests because it determines natural-key identity.

### Mark-scheme points

Matched QP/MS pairs and tagged output provide the source context for extracted points. A point is attached to the best available question parent. The current phase does not claim full question-to-answer alignment; missing alignment must remain visible rather than being inferred as exact.

## 6. Natural keys and idempotence

The question natural key is:

```text
subject code + paper + year + session + variant + question number + sub-label
```

On rerun, ingestion should update enrichment fields and raw text for the existing row, not insert a duplicate. Mark-scheme points use the parent question plus point text as their duplicate key.

Local verification already demonstrated that ingesting the same 9618 fixture twice leaves the same counts: one subject, eight questions, and zero mark-scheme points when no MS rows are available.

## 7. Migration workflow

Configure a local database URL, for example:

```text
DATABASE_URL=sqlite:///./past_paper_ai.db
```

Run the initial migration:

```powershell
alembic upgrade head
```

For PostgreSQL, use a URL such as:

```text
postgresql+psycopg://user:password@localhost:5432/past_paper_ai
```

Inspect migration state with:

```powershell
alembic current
alembic history
```

Every schema change must be a new migration. Do not edit an applied migration in place.

## 8. Verification queries

Count questions by subject:

```sql
SELECT s.code, s.name, COUNT(q.id) AS question_count
FROM subjects AS s
LEFT JOIN questions AS q ON q.subject_id = s.id
GROUP BY s.id, s.code, s.name
ORDER BY s.code;
```

Find duplicate natural keys:

```sql
SELECT subject_id, paper, year, session, variant,
       question_number, sub_label, COUNT(*)
FROM questions
GROUP BY subject_id, paper, year, session, variant,
         question_number, sub_label
HAVING COUNT(*) > 1;
```

Find questions with marks but no points:

```sql
SELECT q.id, q.raw_text, q.marks
FROM questions AS q
LEFT JOIN mark_scheme_points AS p ON p.question_id = q.id
WHERE q.marks > 0
GROUP BY q.id, q.raw_text, q.marks
HAVING COUNT(p.id) = 0;
```

## 9. Future API and application rules

- API responses should expose stable IDs plus source metadata.
- User-owned resources require server-side ownership checks.
- Attempt creation should be idempotent against a client submission token.
- Grading results must record marks possible at grading time.
- Tag/model version and review status should be added before tags drive high-impact recommendations.
- Question source revisions should be versioned or snapshotted.
- Search/filter indexes should be added only after query patterns are measured.

## 10. Future security and operations requirements

- PostgreSQL in production with encrypted connections.
- Separate migration credentials from application runtime credentials.
- Row-level security or equivalent server-side tenant isolation.
- Backups and restore drills.
- Retention rules for answer text and generated artifacts.
- Audit trail for corrections to source text, marks, tags, and grading results.
- PII minimization: the current schema only needs email as a placeholder identity field.

## 11. Open schema decisions

- Whether `questions` should retain `source_file` and page/range provenance directly.
- Whether a separate `question_versions` table is required for source corrections.
- Whether mark-scheme points need an explicit point order and source reference.
- Whether `difficulty` needs confidence and reviewer status.
- Whether topic/subtopic should become foreign keys after normalization.
- Whether `points_awarded` should be JSONB permanently or split into an attempt-points table.
- Whether paper ownership and shared/teacher-curated papers need a separate visibility model.
