"""Offline synthetic journey using real handlers and an ephemeral SQLite store.

No API startup, scheduler, ATS HTTP fetch, notification delivery or live scoring
is invoked. SQLite exercises ORM persistence, not Postgres/pgvector semantics.
"""
import socket
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import Base, Company, Role, Application, ApplicationEvent, DailyBrief
from config import settings
from parsers.base import NormalizedRole
from scan.reconcile import reconcile_company
from scoring.claude_scorer import score_roles
from brief.generator import build_brief
from main import AppCreate, AppUpdate, create_app, update_app, list_app_events


@pytest.fixture
def offline_db(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline journey attempted external I/O")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr("llm.complete", forbidden)
    monkeypatch.setattr(settings, "scoring_mode", "stub")
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    tables = [model.__table__ for model in
              (Company, Role, Application, ApplicationEvent, DailyBrief)]
    Base.metadata.create_all(engine, tables=tables)
    try:
        with Session(engine, autoflush=False) as session:
            yield session
    finally:
        engine.dispose()


def posting(key, title, description="Synthetic platform product requirements"):
    return NormalizedRole(
        ats_job_id=key, title=title, location="San Francisco, CA",
        department="Product", url=f"https://synthetic.invalid/jobs/{key}",
        description=description,
    )


def test_offline_reconciliation_to_application_journey(offline_db):
    db = offline_db
    company = Company(name="Synthetic Journey Labs", tier="A")
    db.add(company)
    db.commit()
    initial = [posting("changed", "Product Manager"),
               posting("closed", "Technical Program Manager"),
               posting("stable", "Platform Product Manager")]
    first = reconcile_company(db, company.id, initial)
    assert (first["new"], first["changed"], first["closed"]) == (3, 0, 0)
    roles = {r.ats_job_id: r for r in db.scalars(select(Role))}
    cost = score_roles(db, list(roles.values()))
    assert cost == {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}
    assert all(r.fit_score == 8 and r.scored_at for r in roles.values())
    stable_scored_at = roles["stable"].scored_at

    board = [posting("changed", "Data Product Manager", "Revised synthetic requirements"),
             initial[2], posting("new", "Technical Product Manager")]
    delta = reconcile_company(db, company.id, board)
    assert (delta["new"], delta["changed"], delta["closed"]) == (1, 1, 1)
    assert delta["changed_ids"] == [roles["changed"].id]
    assert roles["changed"].scored_at is None
    assert roles["changed"].description == "Revised synthetic requirements"
    assert roles["closed"].status == "closed"
    assert roles["stable"].scored_at == stable_scored_at
    new = db.get(Role, delta["new_ids"][0])
    assert new.ats_job_id == "new" and new.source == "ats"
    score_roles(db, [roles["changed"], new])
    assert roles["changed"].scored_at is not None
    assert new.fit_score == 8 and "stub" in new.why_fit.lower()

    today = date(2026, 11, 16)
    brief = build_brief(db, today, delta)
    assert "1 new · 1 changed" in brief.markdown
    assert new.title in brief.markdown and roles["changed"].title in brief.markdown
    assert roles["closed"].title not in brief.markdown
    assert "Nothing overdue" in brief.markdown

    tracked = create_app(AppCreate(role_id=new.id), db)
    assert tracked["stage"] == "watching" and tracked["fit_score"] == 8
    assert create_app(AppCreate(role_id=new.id), db)["id"] == tracked["id"]
    applied = update_app(tracked["id"], AppUpdate(
        stage="applied", next_action="Synthetic follow-up", next_action_due=today), db)
    assert applied["applied_at"] and applied["posting_status"] == "open"
    events = list_app_events(tracked["id"], db)
    assert [(e["from_stage"], e["to_stage"]) for e in events] == [("watching", "applied")]
    update_app(tracked["id"], AppUpdate(stage="applied"), db)
    assert len(list_app_events(tracked["id"], db)) == 1
    updated = build_brief(db, today, delta)
    assert updated.id == brief.id and updated.action_count == 1
    assert "Synthetic follow-up" in updated.markdown and "Applied 1" in updated.markdown
    db.expire_all()
    assert db.get(Application, tracked["id"]).role_id == new.id
    assert db.scalar(select(func.count()).select_from(DailyBrief)) == 1
    assert db.scalar(select(func.count()).select_from(Application)) == 1

    # Repeating the authoritative snapshot does not create or close more roles.
    repeat = reconcile_company(db, company.id, board)
    assert (repeat["new"], repeat["changed"], repeat["closed"]) == (0, 0, 0)


def test_partial_board_does_not_close_missing_roles(offline_db):
    db = offline_db
    company = Company(name="Synthetic Sample Labs")
    db.add(company)
    db.commit()
    board = [posting("one", "Product Manager"), posting("two", "Data Product Manager")]
    reconcile_company(db, company.id, board)
    delta = reconcile_company(db, company.id, [], close_missing=False)
    assert delta["closed"] == 0
    assert all(r.status == "open" for r in db.scalars(select(Role)))
    assert reconcile_company(db, company.id, []) ["closed"] == 2
