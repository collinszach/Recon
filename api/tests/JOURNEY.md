# Synthetic reconciliation journey

Run from the repository root with the API dependencies installed:

```sh
python3 api/tests/test_journey.py
```

The unittest entry point runs its journey cases in a fresh subprocess (also
safe to discover with unittest). It replaces configuration before application
imports, uses only an in-memory SQLite database and synthetic postings at
`example.invalid`, and fails on attempted socket connections or LLM calls.
No services, credentials, migrations, or CI changes are required.

Coverage: new/changed/closed postings, stable identity, unchanged replay,
changed-description score invalidation and stub rescoring, unknown posting
date, closed-role exclusion from the brief, same-day brief update, persisted
watching application and pipeline count, first-scan backfill, sampled-board
omissions, empty authoritative boards, and reopening.

Scope: exercises real reconciliation, scoring, brief functions and ORM models.
Application creation uses the ORM, not the HTTP API. The scorer uses its existing
fixed heuristic; synthetic candidate-profile injection is not supported. This
does not establish live scoring mode, authentication, PostgreSQL compatibility,
ATS fetching, notifications, scheduler behavior, or production health.

No approved journey-spec artifact was present in this source snapshot; these
cases implement the journey described in Ticket 29 and charter Goal 1.

Runner verification (2026-11-09, base `dc723a7` plus these files):

- `python3 api/tests/test_journey.py`: failed before journey execution because
  SQLAlchemy is absent; the subprocess failure is surfaced by unittest.
- `python3 api/tests/test_logic.py`: failed importing missing httpx.
- Installation of existing pinned SQLAlchemy, pgvector and httpx in a temporary
  virtual environment failed because package-index DNS was unavailable.
- `node extension/tests/test-field-matcher.js`: unavailable; Node is not installed.

Passing journey output remains pending on a runner with API dependencies.
