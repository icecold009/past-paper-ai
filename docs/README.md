# Past Paper AI Documentation

This directory contains the seven project reference documents requested for
`past-paper-ai`. They were reviewed against the repository structure and current
implementation on 2026-07-26.

## Documents

1. [Product Requirements Document](01_product_requirements.md) — product vision, users, goals, functional requirements, quality rules, metrics, and open decisions.
2. [Technical Requirements Document](02_technical_requirements.md) — implemented pipeline, repository map, data contracts, CLI, dependencies, database, and technical gaps.
3. [App Flow](03_app_flow.md) — current operator flow plus proposed student navigation, screens, states, permissions, and recovery.
4. [UI/UX Design Brief](04_ui_ux_design_brief.md) — proposed typography, colors, layout, interaction, visual language, and accessibility requirements.
5. [Backend Schema](05_backend_schema.md) — SQLAlchemy/Alembic schema, relationships, ingestion mapping, natural keys, migration workflow, and future decisions.
6. [Implementation Plan](06_implementation_plan.md) — phase gates, current status, exact verification sequence, testing matrix, and delivery protocol.
7. [Security Requirements](07_security_requirements.md) — threat model and requirements for frontend, API, database, auth, RLS, model safety, deployment, operations, and recovery.

## Current implementation boundary

The repository currently provides a local Python batch pipeline:

```text
validate → extract → segment → match → tag → analyze/build-prompt/generate → ingest
```

The phases are deliberately separable. The existing `run` convenience command
does not automatically execute every phase; matching, tagging, generation, and
database ingestion remain explicit reviewable operations.

Current artifacts live under `data/extracted/`, `outputs/`, and `prompts/`.
The future web application, API, authentication, RLS, production PostgreSQL,
deployment, monitoring, and CDN are documented as planned work, not existing
features.

## Source-of-truth map

- Subject and paper configuration: `config/subject_plan.json`
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
