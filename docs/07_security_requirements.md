# Security Requirements

## Purpose

Define the security controls, review obligations, and operational protections for the complete application.

## Status

Draft placeholder. Review the relevant section before shipping any feature in that area.

## Review areas

### Frontend

Client-side data exposure, unsafe rendering, dependency safety, browser storage, and accessibility-related privacy concerns.

### APIs and Backend Logic

Input validation, authorization checks, secret handling, error responses, webhooks, and server-side business rules.

### Database and Storage

Data classification, encryption, backups, retention, migrations, object storage, and least-privilege access.

### Auth and Permissions

Authentication, sessions, password/reset flows, roles, ownership, authorization boundaries, and RLS policies.

### Hosting and Deployment

Deployment protections, environment variables, domains, TLS, headers, preview environments, and release controls.

### Cloud and Compute

Service identity, network boundaries, runtime permissions, regional concerns, and provider configuration.

### CI/CD and Version Control

Branch protection, review requirements, secret scanning, dependency updates, build provenance, and release authorization.

### Security and RLS

Defense-in-depth controls, row-level policies, tenant isolation, policy tests, and fail-closed behavior.

### Rate Limiting

Per-user and per-endpoint limits, abuse detection, Gemini/API quota protection, and graceful throttling responses.

### Prompt Injection

Untrusted-content boundaries, instruction hierarchy, data exfiltration defenses, tool restrictions, and adversarial tests.

### Caching and CDN

Cache keys, private-data isolation, invalidation, stale content, and sensitive response headers.

### Load Balancing and Scaling

Capacity limits, queueing, concurrency controls, horizontal scaling, and degradation behavior.

### Error Tracking and Logs

Structured logs, redaction, alerting, audit events, correlation IDs, and access controls for telemetry.

### Availability and Recovery

Health checks, backups, restore testing, incident response, recovery objectives, and disaster-recovery procedures.
