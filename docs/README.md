# Remote Workforce Monitoring & Productivity Platform — Architecture & Contracts

This folder is the **pre-code architecture and contract set** required by the master
specification (section 104): establish the architecture and contracts first, get approval,
then implement phase-by-phase. No production code has been written yet.

## Documents

| # | Document | Spec 104 item | Contents |
|---|----------|---------------|----------|
| 00 | [Analysis](./00-analysis.md) | 1, 2, 13–16 | ambiguities + defaults, technical/security/scalability risks, component responsibility split |
| 01 | [Architecture](./01-architecture.md) | 3 | system diagram, services, stack, modular backend, deployment, observability, invariants |
| 02 | [Database](./02-database.md) | 4, 5 | ERD + complete Postgres schema, RLS, partitioning, retention, rollups |
| 03 | [API](./03-api.md) | 6 | REST v1 spec, shift API, event ingestion contract, idempotency, webhooks, realtime |
| 04 | [Shift State Machine](./04-shift-state-machine.md) | 7 | states, transitions + guards, tracking modes, computed fields, edge cases |
| 05 | [Desktop Agent](./05-desktop-agent.md) | 8 | service+tray model, collectors, offline queue/sync, security, auto-update |
| 06 | [Frontend Screen Map](./06-frontend-screen-map.md) | 9 | route tree, key screens, role landing/nav, cross-cutting UI |
| 07 | [RBAC & Policy Model](./07-rbac-and-policy-model.md) | 10, 11 | roles, permission matrix, policy inheritance, monitoring/privacy model |
| 08 | [Roadmap & Dependencies](./08-roadmap-and-dependencies.md) | 12, 13 | phased plan (P0–P9), dependency graph, infra, DoD gate |

## Foundational decisions (see doc 00 for rationale)

- **Multi-tenant:** shared schema + `organization_id` + Postgres **Row-Level Security**.
- **Backend is the source of truth** (spec 100): client requests, server validates + records.
- **Stack:** FastAPI + PostgreSQL + Redis + Celery; Next.js/React/TS web; .NET Windows agent;
  S3-compatible object storage; WebSockets + Redis pub/sub for realtime.
- **Attendance is derived** from immutable shift/events (spec 54); never the primary store.
- **High-volume monitoring** tables are partitioned + rolled up for reads.
- **Privacy by design:** never collect passwords, keystroke content, clipboard, private
  messages, or auth tokens; screenshots encrypted + access-logged + retention-bound.

## How to proceed

1. Review docs 00–08 and confirm the ambiguity defaults in doc 00 §1.
2. On approval, implement **Phase 0 + Phase 1** as full vertical slices (see doc 08).
3. Advance phase-by-phase only after each phase's exit criteria pass.
