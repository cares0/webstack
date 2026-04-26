# Feature plan: <feature-name>

| Field | Value |
|---|---|
| Author | |
| Created | YYYY-MM-DD |
| Status | Draft / Approved / In progress / Done |
| Linked contract | `.webstack/contracts/<feature>.yaml` |

## Goal

One sentence. What problem does this feature solve, for whom, and why now?

## User stories

- As a `<persona name from .webstack/personas/>`, I want to `<action>` so that `<benefit>`.
- ...

(One story per row. Cross-reference persona file. If a story is for a non-existent persona, add the persona first.)

## Screens / Routes

| Route | Auth | Description | Server / Client |
|---|---|---|---|
| `/some/path` | required / public | What user sees | Server-rendered / Client island |

## Functions / Behaviors

For each function:
- **Input**: what triggers it (user action, schedule, event).
- **Output**: what changes (UI update, data write, message dispatched).
- **Validation**: business rules.
- **Error states**: what user sees on failure.

## Business rules

- Invariants the system must preserve. Examples:
  - "An order cannot be cancelled after shipping."
  - "A user can have at most 5 active sessions."

(These shape aggregate design — `feature-architect` SubAgent uses them.)

## Data model impact

- **New aggregates**: <list>.
- **Modified aggregates**: <list with field-level changes>.
- **Removed**: <if any>.
- **Migration**: <required? schema change? data backfill?>.

## API surface

Outline (full spec in contract YAML):
- `POST /<resource>`: <one-line>.
- `GET /<resource>/{id}`: <one-line>.
- ...

## Non-functional requirements

- **Performance**: target latency p95 (e.g., < 300ms for read, < 1s for write).
- **Availability**: tolerable downtime per month.
- **Concurrency**: expected RPS / concurrent users.
- **Security**: data classification, auth requirements.

## Out of scope

- ...

## Open questions

- ...

## Tracking

- Backend PR: ...
- Frontend PR: ...
- Infrastructure PR: ...
