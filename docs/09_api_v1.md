# v1 FastAPI service

The repository now includes a small application layer in `api/`. It consumes the reviewed rows loaded by
`src/db/ingest.py` and reuses `src/` and `src/db/` as libraries. The batch pipeline remains separate.

## Local run

After installing `requirements.txt`, configure `DATABASE_URL` and, for answer submission, `GEMINI_API_KEY` in the
local `.env` file. Apply the existing schema migration and start the service:

```powershell
alembic upgrade head
.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

The default development server listens on `http://127.0.0.1:8000`.

## Endpoints

- `GET /subjects` returns database subjects ordered by subject code.
- `GET /questions?subject=&topic=&command_word=&limit=` returns up to 100 questions with source metadata.
- `POST /attempts` accepts `{user_id, question_id, submitted_answer_text}`. It requires stored mark-scheme points,
  validates Gemini's JSON grading result, stores the attempt, and updates the matching mastery cell with a transparent
  recency-weighted average of the latest 20 scored attempts.
- `GET /mastery/{user_id}?subject=` returns available topic/subtopic/command-word cells for the subject. Cells with no
  attempt evidence are returned with score `0` and `has_evidence: false`.
- `POST /papers/generate` accepts a `weak_spot` request with `user_id`, `subject`, and optional `paper`, `target_marks`,
  and `min_real_questions_per_cell`. It ranks the weakest mastery cells, chooses unseen real questions up to the
  configured mark target, and fills sparse cells with Gemini-generated questions. Each returned question has
  `source_type` set to either `real` or `ai_generated`; that provenance is also stored on `paper_questions`.

For this v1, `user_id` is passed directly and checked against the `users` table. It is a development stub, not
authentication or authorization. The Phase 7 identity, ownership, RLS, idempotency-token, request-ID, and audit
requirements remain separate work. The current Phase 4 `mastery` key also has no `subject_id`; the API scopes v1
recalculation and reads through the subject's question dimensions without changing that schema.

The paper endpoint uses the first configured paper in `SUBJECT_PAPER_MARKS` when `paper` is omitted. Its response may
contain fewer marks than the target when no suitable unseen real questions remain and Gemini fallback is unavailable.
