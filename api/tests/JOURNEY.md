# Synthetic journey: ticket #78 diagnosis

Date: 2026-11-10. Outcome: **external dependency failure; stopped as required
by ticket #78. No journey cases executed. Goal 1 remains unverified.**

## Evidence and root cause

The current source export does not contain ticket #71's `JOURNEY.md` or
`test_journey.py`. Diagnosis therefore uses the #71 deliverable supplied with
the approved ticket, not an independently retrieved PR or historical file.
Its recorded worker output was:

```text
Journey setup failed: missing sqlalchemy, pgvector, httpx
Install the existing pinned API dependencies on an approved isolated runner; see api/tests/JOURNEY.md. No journey cases executed.
```

These are existing pinned API dependencies, not dependencies introduced by the
harness. The current runner also lacks all three. This is a runner provisioning
failure before application imports, not evidence of a reconciliation defect.
Per the ticket's explicit external-dependency stop condition, no installation,
harness restoration, application fix or further execution attempt was made.
CI and deployment files were untouched; no network or production access occurred.

## Harness assessment

Static assessment of the supplied #71 diff: the design is reasonable for a
synthetic integration test. A subprocess replaces configuration before application
imports, uses SQLite memory storage and real ORM/journey functions, guards socket
connections and DNS, and forbids LLM completion. Missing dependencies fail rather
than skip. Assertions cover reconciliation, stub scoring, brief generation and
persisted application creation. This is not authentication, HTTP, PostgreSQL or
live scoring coverage. Runtime soundness, including SQLite model compatibility,
remains unknown because setup never completed. The guards are test safeguards,
not independently verified host isolation.

## Current execution evidence

Environment: supplied export `/tmp/hq-code-qxjbdjww/repo`, CPython 3.12.3,
GCC 13.3.0. Revision hash: **unknown**. Both `git status --short` and
`git rev-parse HEAD` returned exit 128 with:

```text
fatal: not a git repository (or any of the parent directories): .git
```

The `.git` directory is empty and read-only; an isolated Git worktree or PR
cannot be established from this export. No test result is attributed to a commit.

Attempt 1 (dependency preflight only), exact command:

```sh
python3 -c "import sys, importlib.util; print('Python:', sys.version); missing = [name for name in ('sqlalchemy', 'pgvector', 'httpx') if importlib.util.find_spec(name) is None]; print('Missing journey dependencies:', ', '.join(missing)); sys.exit(bool(missing))"
```

Exit 1. Complete output:

```text
Python: 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
Missing journey dependencies: sqlalchemy, pgvector, httpx
```

No second attempt: the external-dependency stop condition was established.
The intended journey command `python3 api/tests/test_journey.py` was not run:
the harness is absent and required dependencies are missing. Other project tests
were not run after this stop; this change records evidence only.

`sha256sum api/db.py api/scan/reconcile.py api/scoring/claude_scorer.py api/brief/generator.py api/requirements.txt`
returned exit 0 and the following complete output. All five hashes match the
supplied #71 record; this does not establish a Git revision or harness identity.

```text
8b8ffb79befbe4b64efef57f42a240c2579e454c542937108027206a048e51d0  api/db.py
1d0870c3ac13b0ded8587716d59257e52f245eb745db64d11762a434e6a8a294  api/scan/reconcile.py
1ffb872979a1418032a26aa7c54524cc8110307c84cb129232dce3c602ebb84d  api/scoring/claude_scorer.py
012b0f4954904c12a8076d2c7a92d49e8b915ad0cddfdcb1ee852ea3a2d57307  api/brief/generator.py
2fc4c04067b8f408576fdabf3654a1b9b8ca5ea6d3901b281754a48bbaeb981d  api/requirements.txt
```

Escalation: runner provisioning must supply existing pinned dependencies and
the intended harness in a revision-identifiable isolated checkout. QA Reviewer
verification of an executed journey against that revision is pending; no QA
sign-off is claimed. No substitute mocks or relaxed dependency pins are proposed.

Policy references: supplied `policies/hard-limits.md` (synthetic inputs and no
production authority) and `policies/operating-rules.md` (execution evidence and
two-attempt maximum). Installed policy versions are unknown; no local policy or
ledger records were found in this export.
