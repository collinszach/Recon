# Synthetic reconciliation journey

Run from the repository root on an isolated runner provisioned with the existing
pinned dependencies in `api/requirements.txt`:

```sh
python3 api/tests/test_journey.py
```

The wrapper starts a fresh subprocess. Before application imports the worker
replaces configuration with an in-memory SQLite URL and stub scoring settings,
and blocks socket connections, connection probes, UDP sends and DNS resolution.
It uses only synthetic postings at `example.invalid`; LLM completion is forbidden.
Missing dependencies fail setup explicitly, never skip or pass the journey.
No new dependency, service, credential, migration or CI change is required.
Do not replace SQLAlchemy or the real journey functions with mocks to obtain a pass.

Cases cover new/changed/closed roles, identity, replay, description invalidation,
stub rescoring, unknown posting dates, closed-role brief exclusion, same-day
brief update, persisted watching application and pipeline count, backfill,
sampled omissions, empty authoritative boards and reopening identity.
Application creation uses the ORM, not HTTP. The existing stub uses its fixed
heuristic; this does not test synthetic profile injection, live scoring,
authentication, PostgreSQL, ATS fetching, scheduling or production health.

## Ticket 71 execution evidence — 2026-11-10

Outcome: **setup failure reproduced; full journey remains unverified**.
Stop/escalate after two failed attempts. Next action: provide an approved isolated
runner with existing pinned API dependencies and the intended #29 revision.
No dependency installation, network request, production contact, merge or deploy
was performed. CI and deployment files were not edited.

Environment: supplied source export at `/tmp/hq-code-kk73kmc4/repo`, Linux,
CPython 3.12.3 (GCC 13.3.0), SQLite memory storage configured by the harness.
SQLAlchemy, pgvector and httpx are absent; `python3 -m pip --version` also fails
with `/usr/bin/python3: No module named pip`.

Revision: **unknown**. `git rev-parse HEAD` and `git status --short` fail with
`fatal: not a git repository (or any of the parent directories): .git`.
The supplied `.git` directory is empty and read-only: no Git worktree, branch,
commit or PR can be established here. The #29 harness files were absent and
were restored from the supplied deliverable with dependency diagnostics and
earlier network guards. This is a source-export result, not verification of PR #5.
Relevant source SHA-256 identifiers:

```text
0773f67351621dbaaa41515c65690520955dc66f8a230ee5f6940124b7208ba7  api/tests/test_journey.py
8b8ffb79befbe4b64efef57f42a240c2579e454c542937108027206a048e51d0  api/db.py
1d0870c3ac13b0ded8587716d59257e52f245eb745db64d11762a434e6a8a294  api/scan/reconcile.py
1ffb872979a1418032a26aa7c54524cc8110307c84cb129232dce3c602ebb84d  api/scoring/claude_scorer.py
012b0f4954904c12a8076d2c7a92d49e8b915ad0cddfdcb1ee852ea3a2d57307  api/brief/generator.py
2fc4c04067b8f408576fdabf3654a1b9b8ca5ea6d3901b281754a48bbaeb981d  api/requirements.txt
```

Attempt 1, dependency reproduction, command:
`python3 -c "from sqlalchemy import select"` (exit 1). Complete output:

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'sqlalchemy'
```

Attempt 2, `python3 api/tests/test_journey.py` (Python exit 1; output was captured
in `/tmp/recon-71-journey.txt` and displayed by a shell command whose final `cat`
returned 0). Complete output:

```text
test_isolated_journey (__main__.OfflineJourneyTest.test_isolated_journey) ... FAIL

======================================================================
FAIL: test_isolated_journey (__main__.OfflineJourneyTest.test_isolated_journey)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/hq-code-kk73kmc4/repo/api/tests/test_journey.py", line 134, in test_isolated_journey
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
AssertionError: 1 != 0 : Journey setup failed: missing sqlalchemy, pgvector, httpx
Install the existing pinned API dependencies on an approved isolated runner; see api/tests/JOURNEY.md. No journey cases executed.


----------------------------------------------------------------------
Ran 1 test in 0.068s

FAILED (failures=1)
```

## Verification

- `python3 -m py_compile api/tests/test_journey.py`: passed.
- Import with `importlib.util.spec_from_file_location` under a socket guard:
  passed; `db`, `config`, `llm`, `sqlalchemy` were not imported and unittest
  discovery found exactly one subprocess wrapper case. No journey ran here.
- Full journey: failed setup as recorded above; both inner cases unexecuted.
- Existing logic and extension tests: not run after the two-failure stop;
  they do not validate this setup-only change.
- Git diff/branch/PR and revision verification: unavailable, no usable Git metadata.
- Installed policy versions, live state and release readiness: unknown; no claim.

Policy references: supplied `policies/hard-limits.md` (synthetic inputs, no
production authority) and `policies/operating-rules.md` (execution evidence and
two-attempt stop). No local policy or ledger files were present in the export.
