"""Record background job runs so their health is visible in the app."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db import JobRun


class _Run:
    def __init__(self, row: JobRun):
        self.row = row
        self.summary: str | None = None
        self.detail = None
        self.error: str | None = None

    def fail(self, reason: str | None) -> None:
        self.error = reason or "failed"


@contextmanager
def record(db: Session, kind: str):
    """with record(db, "mail") as run: ... — writes started/finished/status.

    An exception inside the block is recorded as an error and re-raised, so
    callers keep their own handling.
    """
    row = JobRun(kind=kind, started_at=datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    run = _Run(row)
    try:
        yield run
    except Exception as e:
        db.rollback()
        run.error = f"{type(e).__name__}: {e}"
        _finish(db, row, run)
        raise
    _finish(db, row, run)


def _finish(db: Session, row: JobRun, run: _Run) -> None:
    row = db.merge(row)
    row.finished_at = datetime.now(timezone.utc)
    row.status = "error" if run.error else "ok"
    row.summary = (run.error if run.error else run.summary)[:500] if (run.error or run.summary) else None
    try:
        row.detail = json.dumps(run.detail, default=str)[:20000] if run.detail is not None else None
    except (TypeError, ValueError):
        row.detail = None
    db.commit()
