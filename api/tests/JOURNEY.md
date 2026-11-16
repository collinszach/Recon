# Ticket #124: offline journey evidence

Date: 2026-11-16. Supplied base revision:
`dc723a72850b98ed8116cfdb9702ad449566a4b7`.
This source export has no git history. The run includes the local changes in
this ticket; it is not evidence of an identified PR-head SHA.

## Prior evidence correction

The supplied #113 evidence says no journey harness existed, rather than that
database-dependent journey tests skipped. This export likewise had only
`api/tests/test_logic.py`, with no pytest test function, and no JOURNEY.md.
There were no existing Postgres/Redis-backed tests here to change or weaken.

## Changes

- Added `test_journey.py`, using real SQLAlchemy models and production handlers
  against a fresh in-memory SQLite database with foreign keys enabled.
- Exercised synthetic normalized ATS board snapshots: insertion, changed
  descriptions and score invalidation, missing-role closure, unchanged roles,
  repeated snapshots, and partial-board closure protection.
- Called the public scoring dispatcher with stub mode forced locally. Asserted
  persisted scores, explanations, timestamps and zero token usage. This uses
  the existing title/company-tier heuristic, not a configurable candidate
  profile or evidence of ranking quality.
- Generated and persisted the brief, then tracked a role through the existing
  application handlers, verified duplicate prevention and stage-event history,
  and regenerated the same day's brief with a due follow-up and pipeline count.
- Added a pytest entry point for the existing accumulated logic checks.

Only synthetic employers, roles, descriptions, URLs and application actions are
created. Socket connection/DNS attempts and LLM completion calls fail the offline
tests. No API startup or scheduler is invoked. No production code, dependencies,
CI, deployment files or production configuration changed.

## Execution

Command, from repository root: `python -m pytest -q`

Exit code: **0**. Raw final summary line:

```text
3 passed, 2 warnings in 0.93s
```

| Test | Result |
| --- | --- |
| `api/tests/test_journey.py::test_offline_reconciliation_to_application_journey` | Passed |
| `api/tests/test_journey.py::test_partial_board_does_not_close_missing_roles` | Passed |
| `api/tests/test_logic.py::test_logic_checks` | Passed |

One full-suite run, zero failed attempts, zero failures, zero skips. Both
warnings are existing FastAPI `on_event` deprecation warnings from importing
the application handlers.

## Limits and PR handoff

SQLite verifies the offline synthetic handler journey, not PostgreSQL/pgvector
behavior, Redis workers, ATS HTTP parsers, FastAPI request routing/startup,
notification delivery, live scoring or production operation. Those integrations
were not exercised; they were not collected as skipped tests. Network access is
off and no Postgres/Redis services are supplied. Goal 1's offline synthetic path
now has execution evidence; production end-to-end acceptance remains unverified.

Suggested PR title: `Exercise the synthetic reconciliation journey offline`.
No PR was opened from this history-free workspace. CI on the eventual PR head
in the disposable VM remains required merge evidence. This run grants no merge
or release approval.
