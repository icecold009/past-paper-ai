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
- `GET /guidance/{user_id}?subject=` returns the next personalized diagnostic, practice, or review recommendation
  with the topic, command word, question, and reason for the recommendation.
- `GET /questions?subject=&topic=&command_word=&chapter_id=&limit=` returns up to 100 questions with source metadata. When
  `chapter_id` is supplied, only questions with an approved mapping to that chapter are returned.
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
  Optional TypeSafe selection is server-side and disabled by default. Accepted recommendation responses include additive
  `decision_source`, `decision_version`, `decision_confidence`, and `provider_model` provenance fields.
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

## Optional TypeSafe guidance selection

Configure the server with `TYPESAFE_GUIDANCE_MODE=off|shadow|active`. `off` is the safe default. `shadow` may call a
configured provider but continues returning the deterministic recommendation. `active` uses a provider result only when
it names one of the bounded, application-generated candidates and meets `TYPESAFE_MIN_CONFIDENCE`; failures fall back
to deterministic guidance.

The provider request contains only subject/stage context, curriculum version, derived chapter states, and stable candidate
IDs such as `chapter:42:practice`. It does not contain raw student answers, question or mark-scheme text, user email,
school identifiers, credentials, or authentication tokens. `TYPESAFE_API_URL` remains an explicit deployment setting so
the provider adapter can be aligned with the verified live TypeSafe API contract before activation.
