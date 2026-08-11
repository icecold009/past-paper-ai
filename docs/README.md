# Past Paper AI Documentation

This directory contains the project reference documents requested for
`past-paper-ai`. They were reviewed against the repository structure and current
implementation on 2026-07-26.

## Product north star

Past Paper AI is intended for Cambridge students in Grades 8–12 at the target
school. Its distinctive purpose is to identify each student’s weak subjects and
chapters, explain why they need attention, and provide targeted help and
practice. It should feel like a personal Cambridge learning coach—not a generic
AI chat website.

## Documents

1. [Product Requirements Document](01_product_requirements.md) — product vision, users, goals, functional requirements, quality rules, metrics, and open decisions.
2. [Technical Requirements Document](02_technical_requirements.md) — implemented pipeline plus the curriculum-map, diagnostic, and recommendation architecture needed for personalization.
3. [App Flow](03_app_flow.md) — operator flow plus student onboarding, diagnosis, chapter support, targeted practice, and future navigation.
4. [UI/UX Design Brief](04_ui_ux_design_brief.md) — proposed visual system for a calm, explainable Cambridge learning workspace.
5. [Backend Schema](05_backend_schema.md) — current SQLAlchemy/Alembic schema plus required curriculum, evidence, recommendation, and school-scope extensions.
6. [Implementation Plan](06_implementation_plan.md) — phase gates centered on the diagnosis → targeted help → improvement loop.
7. [Security Requirements](07_security_requirements.md) — threat model and requirements for frontend, API, database, auth, RLS, student privacy, model safety, deployment, operations, and recovery.
8. [Project Backlog](08_backlog.md) — incomplete tasks, blockers, product decisions, priorities, dependencies, and acceptance criteria.

9. [v1 API](09_api_v1.md) - local FastAPI run instructions, endpoint contracts, and v1 limitations.

## Current implementation boundary

The repository currently provides a local Python batch pipeline:

```text
validate → extract → segment → match → tag → analyze/build-prompt/generate → ingest
```

The phases are deliberately separable. The existing `run` convenience command
does not automatically execute every phase; matching, tagging, generation, and
database ingestion remain explicit reviewable operations.

Current artifacts live under `data/extracted/`, `outputs/`, and `prompts/`.
The v1 FastAPI service now exists alongside the batch pipeline. Authentication,
deployment, monitoring, and CDN are documented as planned work, not existing
features. The current code does not yet contain the target school’s Grade 8–12
curriculum map, diagnostic engine, chapter-level weakness profile, or
recommendation service; those are explicitly planned next-stage requirements.

## Source-of-truth map

- Subject and paper configuration: `config/subject_plan.json`
- Variant scope and paper marks: `config/subject_plan.json` and `src/subject_plan.py`
- Filename parsing and normalized metadata: `src/utils.py`
- Canonical paths: `src/paths.py`
- CLI commands: `src/cli.py`
- Question structure and marks: `src/segment_questions.py`
- QP/MS pairing: `src/match_mark_schemes.py`
- Gemini batch enrichment: `src/tag_questions.py`
- Relational schema: `src/db/models.py` and Alembic migrations
- Ingestion: `src/db/ingest.py`
- Agent workflow rules: `AGENTS.md` and `.github/agents/past-paper-ai-pipeline.agent.md`

When a document and implementation disagree, verify the code and update the
document in the same scoped change. Do not describe a planned control as
implemented without a reproducible check.
