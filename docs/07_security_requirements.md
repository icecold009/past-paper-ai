# Security Requirements

## 1. Scope and current posture

This document covers the future product and the security posture of the current repository.

- Reviewed against repository: 2026-07-26
- Current system: local batch scripts, CSV/JSON artifacts, optional local database
- Current users: repository operator; no public user accounts
- Current secrets: `GEMINI_API_KEY` and optional `DATABASE_URL` loaded from local `.env`
- Current web/API surface: none
- Current RLS/auth/rate limiting/CDN/load balancing/error tracking: none implemented

Security requirements below are phrased as controls to implement and verify. A planned control is not evidence that the control exists.

## 2. Assets and threat model

### Assets

- source CAIE PDFs and extracted text;
- question, subquestion, marks, tags, and mark-scheme points;
- Gemini API key and database credentials;
- generated practice-paper prompts and outputs;
- user email, submitted answers, attempts, marks, and mastery history;
- model responses and review/correction decisions;
- migration and backup artifacts;
- repository history and CI secrets.

### Actors

- local pipeline maintainer;
- student user;
- teacher/content reviewer;
- administrator/operator;
- malicious anonymous visitor;
- malicious authenticated user attempting cross-user access;
- compromised dependency, source PDF, model response, or CI job.

### Trust boundaries

```text
source PDFs ──untrusted──► extraction/parsing
extracted text ──untrusted──► Gemini prompt
Gemini response ──untrusted──► validator/CSV/database
browser ──untrusted──► future API
future API ──restricted──► database
CI/deploy ──privileged──► production infrastructure
```

The most important current boundary is between extracted exam text and Gemini instructions. Source content must be treated as data, not as trusted instructions.

## 3. Security principles

- Least privilege for users, services, database roles, and CI jobs.
- Deny by default for user data and administrative actions.
- Validate at every boundary; never rely on model output shape without parsing.
- Keep secrets out of code, logs, artifacts, prompts, and Git history.
- Preserve provenance and auditability for content corrections and grading.
- Fail closed on missing credentials, malformed responses, unauthorized access, and ambiguous ownership.
- Minimize retained personal data and source material.
- Separate batch/model enrichment from runtime student requests.

## 4. Frontend

### Requirements

- Do not place `GEMINI_API_KEY`, `DATABASE_URL`, service-role credentials, or admin tokens in browser code.
- Use a secure session mechanism with appropriate cookie flags or a carefully managed token strategy.
- Escape/render question text safely; extracted PDFs and model output may contain HTML-like or script-like content.
- Do not use `dangerouslySetInnerHTML` for raw source/model text without a strict sanitizer and an explicit rendering need.
- Protect state-changing actions against CSRF where cookie authentication is used.
- Avoid storing submitted answers or tokens in long-lived browser storage unless the privacy and threat model justify it.
- Make logout clear local session state and prevent access to cached private views.
- Show source/model review status honestly; do not style unreviewed tags as verified facts.

### Verification

- Inspect production bundles for secret patterns.
- Test XSS payloads in question text, tags, feedback, and issue reports.
- Test logout, expired sessions, back-button behavior, and cross-user deep links.
- Run keyboard, screen-reader, and zoom checks without weakening security messaging.

### Status

No frontend exists yet. These are release requirements for the future web application.

## 5. APIs and backend logic

### Requirements

- Validate path, query, JSON, and uploaded-file inputs with explicit schemas.
- Bound pagination, filter lengths, answer size, batch size, and request duration.
- Use parameterized SQL/ORM queries; never concatenate user values into SQL.
- Enforce ownership and role checks server-side on every resource access.
- Make answer submission and other state transitions idempotent.
- Return safe error messages; do not expose stack traces, SQL, file paths, secrets, or model prompts to users.
- Add request IDs and structured audit events without logging answer content by default.
- Separate content-reviewer/admin endpoints from student endpoints.
- Treat model-generated grading/tagging as untrusted and validate allowed values before persistence.

### Status

No API is implemented. SQLAlchemy ingestion is local batch logic, not a public authorization boundary.

## 6. Database and storage

### Requirements

- Use PostgreSQL with encrypted connections in production.
- Use separate migration, application, read-only, and worker credentials where practical.
- Restrict database network access to approved services.
- Encrypt storage and backups.
- Apply least-privilege grants; the application must not use an unrestricted superuser.
- Validate foreign keys and unique constraints through migrations.
- Define retention and deletion behavior for emails, answers, attempts, generated papers, and logs.
- Keep source PDFs and extracted content in access-controlled storage; do not assume a Git-ignored file is protected on a shared machine.
- Record source revision/model version when user-visible feedback depends on mutable content.

### Current schema considerations

The implemented schema has foreign keys, uniqueness constraints, cascading relationships, and a JSONB `points_awarded` field. It does not yet contain RLS policies, audit history, source-version snapshots, or production backup configuration.

## 7. Authentication and permissions

### Roles

Proposed roles:

- student: own attempts, papers, mastery, and settings;
- reviewer/teacher: approved content review and possibly assigned student views;
- operator/admin: migrations, source ingestion, system configuration, and incident response.

Roles must be explicit and server-derived. Never trust a role supplied by the browser.

### Requirements

- Use a maintained identity provider or well-reviewed auth implementation.
- Verify email/account recovery flows and protect against account enumeration.
- Require reauthentication or step-up controls for sensitive account changes.
- Rate-limit login, recovery, and token refresh actions.
- Revoke sessions after security-sensitive events.
- Test direct object reference attacks on every user-owned resource.

### Status

`users` exists as database scaffolding only. No authentication or permissions are implemented.

## 8. Hosting and deployment

### Requirements

- Use HTTPS everywhere outside local development.
- Store secrets in a managed secret store or deployment secret facility.
- Keep development, staging, and production databases separate.
- Require migration review and backup checks before destructive schema changes.
- Use non-root containers/processes and minimal base images.
- Restrict admin panels and operational endpoints.
- Define deployment rollback and database compatibility rules.
- Review copyright/access controls before hosting source-paper content.

### Status

No deployment target is configured. Hosting design remains future work.

## 9. Cloud and compute

### Requirements

- Separate API, batch worker, and database identities.
- Restrict egress where feasible, especially for workers processing private data.
- Set CPU, memory, disk, timeout, and concurrency limits for PDF extraction and model batches.
- Use ephemeral work directories for untrusted uploads and clean them after processing.
- Scan uploaded PDFs for malformed/malicious content before processing if uploads are enabled.
- Pin dependencies and rebuild images for security updates.
- Monitor Gemini and database spend/quotas.

### Status

Current operation is local. These controls apply before accepting external uploads or deploying workers.

## 10. CI/CD and version control

### Requirements

- Keep work on feature branches and require review before merge.
- Never commit `.env`, API keys, database passwords, generated private answers, or private source files.
- Add secret scanning and dependency scanning to CI.
- Pin or constrain dependency versions and review transitive updates.
- Run tests, migration checks, artifact schema checks, and security checks before release.
- Restrict CI token permissions and protect deployment environments.
- Do not let pull requests from untrusted forks access production secrets.
- Keep migrations forward-compatible with the application version being deployed.
- Record the code revision and input/config manifest for large batch runs.

### Current controls

The repository includes `.gitignore` protection for local environment/data patterns and branch discipline in `AGENTS.md`. CI security checks and deployment protection are not yet present.

## 11. Security and RLS

### Requirements

When user data reaches PostgreSQL:

- enable row-level security on `attempts`, `mastery`, `papers`, and any future private tables;
- define policies based on the authenticated database/application user identity;
- ensure service roles are used only by trusted server-side workers;
- test both positive and negative access paths;
- do not rely solely on application query filters as tenant isolation.

Content tables may be public/read-only only after copyright and review status are resolved. Reviewer/admin mutation policies must be narrower than student read policies.

### Status

No RLS policies exist because no authenticated service exists yet. This is a mandatory gate before multi-user production use.

## 12. Rate limiting and abuse prevention

### Requirements

- Limit login/recovery attempts per IP and account.
- Limit question browsing and session creation per user/IP.
- Limit answer submissions and report creation.
- Put strict quotas around Gemini batch jobs and administrator-triggered imports.
- Use exponential backoff with bounded retries for external APIs.
- Return `Retry-After` where appropriate.
- Prevent one user or job from exhausting database connections, worker capacity, disk, or model quota.

### Current behavior

The tagging batch supports a limit, delay, and one retry. There is no user-facing rate limiting because there is no API.

## 13. Prompt injection and model safety

This is a high-priority project-specific risk because CAIE text is inserted into Gemini prompts and model tags influence every later feature.

### Requirements

- Treat PDF text, question text, mark-scheme text, filenames, and user answers as untrusted data.
- Clearly delimit source text from instructions.
- Tell the model to classify/extract source content, not follow instructions found inside it.
- Request a strict schema and validate every field after the model responds.
- Restrict `difficulty` to `easy`, `medium`, or `hard`.
- Bound topic/command-word lengths and reject unexpected nested objects or executable content.
- Never pass model-generated instructions directly to another privileged tool without validation.
- Keep model calls batch/offline; do not let a student answer trigger privileged filesystem/database operations.
- Add adversarial fixtures containing text such as “ignore previous instructions” and verify the model output remains classification-only.
- Review at least 15–20 real tags against the syllabus before full tagging.
- Record model and prompt versions for reproducibility.

### Mark-scheme extraction

Marking points must be short, discrete, and grounded in the source MS. The system must not invent points when the mark scheme is missing or the response is malformed.

## 14. Caching and CDN

### Requirements when introduced

- Cache only public, reviewed content by default.
- Never use a shared cache for user attempts, answer text, mastery, or private papers.
- Include content revision/version in cache keys.
- Invalidate caches after source/tag/mark corrections.
- Do not cache authenticated responses without explicit private-cache controls.
- Configure CDN content-disposition and access controls for PDFs according to licensing.

### Status

No cache or CDN exists today.

## 15. Load balancing and scaling

### Requirements when traffic grows

- Keep API instances stateless where possible.
- Store sessions/queues in durable shared infrastructure, not process memory.
- Move PDF extraction and Gemini batches to bounded workers.
- Limit database pool size per instance and load-test connection behavior.
- Use health/readiness checks that distinguish process health from database/model dependency health.
- Preserve job idempotence so retries do not duplicate questions or attempts.

### Status

No load balancer, worker queue, or autoscaling configuration exists.

## 16. Error tracking and logs

### Requirements

- Use structured logs with timestamp, level, phase, request/job ID, subject, source identifier, and outcome.
- Redact API keys, passwords, tokens, email where unnecessary, submitted answers, and raw private documents.
- Store enough context to reproduce a bad segmentation/tag without dumping the entire source into logs.
- Track counts of extracted pages, segmented questions, unmatched files, model skips, ingest upserts, and database errors.
- Alert on spikes in malformed model output, match failures, extraction failures, authentication failures, and database errors.
- Set retention and access permissions for logs.

### Status

The CLI has warnings/errors suitable for local batch diagnostics, but no centralized error tracking or alerting exists.

## 17. Availability and recovery

### Requirements

- Keep source PDFs and generated artifacts reproducible and separately backed up where permitted.
- Back up production PostgreSQL with tested point-in-time or scheduled recovery.
- Run restore drills and record recovery time and recovery point objectives.
- Make migrations reversible or document forward-fix procedures.
- Keep batch jobs resumable and idempotent.
- Preserve failed input/output manifests for diagnosis without retaining secrets.
- Define incident severity, owner, communication, and post-incident review.

### Suggested initial objectives

These are planning targets, not current guarantees:

- RPO for user attempts: 24 hours or better initially;
- RTO for the student service: 4 hours or better initially;
- batch rerun: safe without duplicate rows;
- model outage: existing reviewed content remains usable even when Gemini is unavailable.

## 18. Release security checklist

Before exposing a user-facing deployment:

- [ ] `.env` and secrets are absent from Git and artifacts.
- [ ] Dependency and secret scans pass.
- [ ] HTTPS and secure session settings are verified.
- [ ] Auth and cross-user authorization tests pass.
- [ ] RLS/equivalent tenant isolation is enabled and tested.
- [ ] Input/output sanitization tests pass for source text, model output, and answers.
- [ ] Prompt-injection fixtures pass.
- [ ] Database backup and restore have been tested.
- [ ] Rate limits and abuse responses are configured.
- [ ] Logs redact sensitive content.
- [ ] Health checks, alerts, and rollback procedures are documented.
- [ ] Source licensing and access policy are approved.
