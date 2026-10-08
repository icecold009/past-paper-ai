# v1 FastAPI service

The repository now includes a small application layer in `api/`. It consumes the reviewed rows loaded by
`src/db/ingest.py` and reuses `src/` and `src/db/` as libraries. The batch pipeline remains separate.

## Local run

After installing `requirements.txt`, configure `DATABASE_URL` and `AUTH_SECRET` in the local `.env` file. The service
defaults to blocking AI calls that would process student answers or derived student weakness data. Answer grading
returns `503` and paper generation uses real questions only while that approval gate is closed. A configured
`GEMINI_API_KEY` alone does not open the gate. Apply the existing schema migration and start the service:

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
  persisted with `PUT /diagnostics/{diagnostic_id}/responses/{question_id}`. The answer payload user must match the
  authenticated resource owner; mismatches are rejected before persistence. Diagnostics are closed with
  `POST /diagnostics/{diagnostic_id}/submit`; scoring remains a separate reviewed grading policy.
- `POST /practice/sessions` creates an active retry-safe session, while the answer and submit endpoints persist its state
  without silently fabricating marks. Practice-answer payload identity is checked against both the authenticated owner
  and the practice-session owner.
- `GET /privacy/export` downloads the authenticated student's profile and app-held attempts, mastery, papers, diagnostics,
  recommendations, evidence, and practice-session records as JSON. The response is marked `no-store`; shared
  Cambridge question and mark-scheme content is referenced by ID and not copied into the export. The export includes
  AI-generated question text, marks, and mark-scheme points only when the requesting student's paper is the sole owner.
  Generated content with missing or ambiguous ownership is omitted and marked unavailable. The current schema/API does not store
  student notes or uploaded school-exam files; any future notes/file intake must be added to the export and deletion
  scope before it is enabled.
- `DELETE /privacy/account` deletes the authenticated student's application-database profile and user-owned rows after
  the request body confirms `DELETE MY DATA`. It is idempotent for an already-deleted profile and preserves shared
  question, curriculum, and subject records. It removes the student's generated questions and mark-scheme points when
  no other records reference them; otherwise it clears their text, marks, and generated topic metadata while preserving
  referenced IDs. Orphaned AI-generated questions left by earlier deletions are scrubbed by migration 0007. That data
  cleanup is irreversible and its downgrade intentionally does not restore private text.

AI-generated questions are private to the student whose paper owns them. The public `GET /questions` catalog and
diagnostic selection exclude them. Attempt grading and practice-session creation require a single unambiguous owner
matching the authenticated student; ownerless or multiply owned generated questions are unavailable. Real Cambridge
questions remain in the shared catalogue and retain their existing content behavior.

Personal endpoints, including `/attempts`, `/mastery/{user_id}`, `/papers/generate`, guidance, diagnostics,
recommendation dismissal, practice sessions, and both `/privacy` routes, require an HMAC-verified Bearer token and enforce self-ownership
against an active user record. User IDs in paths and request payloads must match the token subject. `AUTH_SECRET` and
the token helper are a local/test boundary, not customer authentication: there is no login flow, token revocation,
school-role authorization, or PostgreSQL RLS. Do not treat this API as production-ready authentication.

The privacy endpoints operate only on the active application database. They do not erase database backups, logs,
provider-side copies, school systems, exported files, or other systems outside that database. No retention period,
consent/notice process, school access rule, legal basis, or regional eligibility decision is set by these routes. They
are technical controls for this API slice, not evidence of production authentication or a complete privacy program.

The paper endpoint uses the first configured paper in `SUBJECT_PAPER_MARKS` when `paper` is omitted. Its response may
contain fewer marks than the target when no suitable unseen real questions remain and Gemini fallback is unavailable.

## Optional TypeSafe guidance selection

Configure the selector with `TYPESAFE_GUIDANCE_MODE=off|shadow|active`. `off` is the selector's safe default. Independently,
the application also defaults its student-data AI approval gate to closed; while closed, guidance never calls the
selector, even if `shadow` or `active` is configured. The application gate must not be opened until the provider and
school/policy review is complete. When approved and opened by application composition, `shadow` may call a configured
provider but continues returning the deterministic recommendation. `active` uses a provider result only when it names
one of the bounded, application-generated candidates and meets `TYPESAFE_MIN_CONFIDENCE`; failures fall back to
deterministic guidance.

The provider request contains only subject/stage context, curriculum version, derived chapter states, and stable candidate
IDs such as `chapter:42:practice`. It does not contain raw student answers, question or mark-scheme text, user email,
school identifiers, credentials, or authentication tokens. `TYPESAFE_API_URL` remains an explicit deployment setting so
the provider adapter can be aligned with the verified live TypeSafe API contract before activation.

