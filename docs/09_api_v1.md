# v1 FastAPI service

The repository now includes a small application layer in `api/`. It consumes the reviewed rows loaded by
`src/db/ingest.py` and reuses `src/` and `src/db/` as libraries. The batch pipeline remains separate.

## Local run

After installing `requirements.txt`, configure `DATABASE_URL`, `AUTH_SECRET`, and, for answer submission,
`GEMINI_API_KEY` in the local `.env` file. Apply the existing schema migration and start the service:

```powershell
alembic upgrade head
.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

The default development server listens on `http://127.0.0.1:8000`.

## Endpoints

- `GET /healthz` is a process liveness check; `GET /readyz` verifies database readiness. Responses include an
  `X-Request-ID` header for tracing.
- `GET /subjects` returns database subjects ordered by subject code.
- `GET /questions?subject=&topic=&command_word=&limit=` returns up to 100 questions with source metadata.
- `POST /attempts` accepts `{user_id, question_id, submitted_answer_text}`. It requires stored mark-scheme points,
  validates Gemini's JSON grading result, stores the attempt, and updates the matching mastery cell with a transparent
  recency-weighted average of the latest 20 scored attempts. Attempts retain the grading model, policy version, and
  grading status for later review/correction workflows.
- `GET /mastery/{user_id}?subject=` returns available topic/subtopic/command-word cells for the subject. Cells with no
  attempt evidence are returned with score `0` and `has_evidence: false`.
- `POST /papers/generate` accepts a `weak_spot` request with `user_id`, `subject`, and optional `paper`, `target_marks`,
  and `min_real_questions_per_cell`. It ranks the weakest mastery cells, chooses unseen real questions up to the
  configured mark target, and fills sparse cells with Gemini-generated questions. Each returned question has
  `source_type` set to either `real` or `ai_generated`; that provenance is also stored on `paper_questions`.
- `GET /curriculum/{subject}` returns only approved, versioned school chapters.
- `GET /guidance/{user_id}?subject=` returns `no_content`, `start_diagnostic`, `needs_practice`, or `on_track`, based on
  at least two scored attempts per chapter. It stores evidence and a deterministic, versioned recommendation reason.
- `POST /diagnostics` creates a retry-safe baseline question set from approved chapter mappings. Diagnostic answers are
  persisted with `PUT /diagnostics/{diagnostic_id}/responses/{question_id}` and closed with
  `POST /diagnostics/{diagnostic_id}/submit`; scoring remains a separate reviewed grading policy.
- `POST /practice/sessions` creates an active retry-safe session, while the answer and submit endpoints persist its state
  without silently fabricating marks.

The legacy `/attempts`, `/mastery/{user_id}`, and `/papers/generate` endpoints still accept a direct `user_id` for
backward-compatible local development. The new personalized state-changing endpoints require an HMAC-verified Bearer
token and enforce user/school ownership. `AUTH_SECRET` is only a local cryptographic boundary until a school-approved
identity provider and PostgreSQL RLS policies are integrated; do not treat the current development mode as production
authentication.

The paper endpoint uses the first configured paper in `SUBJECT_PAPER_MARKS` when `paper` is omitted. Its response may
contain fewer marks than the target when no suitable unseen real questions remain and Gemini fallback is unavailable.
