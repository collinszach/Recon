"""Company news, end to end through the API: fetch -> dedupe -> store -> serve.

Runs against an in-memory SQLite DB with a fake provider, so it needs the API's
Python dependencies (pip install -r api/requirements.txt) but no Postgres and
no network. Run: `python3 api/tests/test_news_api.py`.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
from db import Application, Base, Company, CompanyNews, DailyBrief, JobRun, Role  # noqa: E402
from news import runner  # noqa: E402
from news.base import Article, NewsProvider  # noqa: E402

failures: list[str] = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine, tables=[t.__table__ for t in
                                         (Company, Role, Application, CompanyNews, JobRun, DailyBrief)])
Session = sessionmaker(bind=engine, autoflush=False)


def override_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[main.get_db] = override_db
client = TestClient(main.app)   # not a context manager: skips the Postgres-only startup hook

now = datetime.now(timezone.utc)


class FakeProvider(NewsProvider):
    name = "fake"
    daily_budget = 10
    min_interval_sec = 0

    def __init__(self):
        self.calls: list[list[str]] = []

    def enabled(self):
        return True

    def fetch(self, phrases, since):
        self.calls.append(phrases)
        if phrases == ["Rocket Lab"]:
            return [
                Article("Rocket Lab raises $40M Series B - Reuters",
                        "https://www.reuters.com/a?utm_source=x", "Reuters", None, now - timedelta(hours=3)),
                # same story syndicated: must be dropped
                Article("Rocket Lab raises $40M Series B | Yahoo",
                        "https://finance.yahoo.com/b", "Yahoo", None, now - timedelta(hours=2)),
                # same URL modulo tracking params: must be dropped
                Article("Rocket Lab funding round", "https://reuters.com/a", "Reuters", None, now),
                # doesn't name the company: must be dropped
                Article("Space stocks rally on launch hopes", "https://x.com/c", "X", None, now),
                Article("Rocket Lab unveils Neutron fairing", "https://spacenews.com/d",
                        "SpaceNews", None, now - timedelta(days=3)),
                Article("Rocket Lab founder profile", "https://old.com/e", "Old", None,
                        now - timedelta(days=60)),
            ]
        if phrases == ["Peloton"]:
            return [Article("Peloton lays off 6% of staff", "https://cnbc.com/p", "CNBC", None,
                            now - timedelta(hours=5))]
        raise RuntimeError("provider exploded")   # Flaky Co: must not end the run


fake = FakeProvider()
runner.active_provider = lambda: fake

with Session() as db:
    rl = Company(name="Rocket Lab", tier="A", ats_name="greenhouse")
    pel = Company(name="Peloton", tier="B", ats_name="greenhouse")
    flaky = Company(name="Flaky Co", tier="C", ats_name="lever")
    auto = Company(name="Some Search Employer", tier="B", ats_name="jsearch")   # not tracked
    gone = Company(name="Dismissed Inc", tier="B", ats_name="ashby", dismissed_at=now)
    db.add_all([rl, pel, flaky, auto, gone])
    db.commit()
    peloton_role = Role(company_id=pel.id, ats_job_id="p1", title="PM Intern")
    db.add(peloton_role)
    db.commit()
    db.add(Application(role_id=peloton_role.id, company_name="Peloton", stage="applied"))
    db.commit()
    RL, PEL, FLAKY, AUTO = rl.id, pel.id, flaky.id, auto.id

# ── fetch ──────────────────────────────────────────────────────────────────
r = client.post("/api/news/run")
check("run status", r.status_code, 200)
res = r.json()
check("run ok despite one failing company", res["status"], "ok")
check("tracked excludes search employers + dismissed", res["tracked"], 3)
check("errors recorded", len(res["errors"]), 1)
check("added", res["added"], 4)   # 3 Rocket Lab (one is 60d old) + 1 Peloton
check("applied company queried first", fake.calls[0], ["Peloton"])

# A second scheduled run the same day is gated, not re-fetched.
with Session() as db:
    check("gate", runner.run_news_fetch(db)["status"], "skipped")
# A forced run re-fetches everything but stores no duplicates.
check("idempotent", client.post("/api/news/run").json()["added"], 0)

# ── GET /api/companies/{id}/news ───────────────────────────────────────────
r = client.get(f"/api/companies/{RL}/news")
check("news status", r.status_code, 200)
items = r.json()
check("30-day window drops old article", len(items), 2)
check("newest first", [i["title"] for i in items],
      ["Rocket Lab raises $40M Series B - Reuters", "Rocket Lab unveils Neutron fairing"])
check("tags", items[0]["tags"], ["funding"])
check("shape", sorted(items[0]), sorted(["id", "company_id", "title", "url", "source", "description",
                                         "published_at", "tags", "provider"]))
check("wider window", len(client.get(f"/api/companies/{RL}/news?days=90").json()), 3)
check("limit", len(client.get(f"/api/companies/{RL}/news?limit=1").json()), 1)
check("404", client.get("/api/companies/99999/news").status_code, 404)
check("company without news", client.get(f"/api/companies/{FLAKY}/news").json(), [])

# ── GET /api/news ──────────────────────────────────────────────────────────
check("recent all", len(client.get("/api/news").json()), 3)
lay = client.get("/api/news?tag=layoffs").json()
check("tag filter", [(n["company_name"], n["tags"]) for n in lay], [("Peloton", ["layoffs"])])
check("tag no partial match", client.get("/api/news?tag=lay").json(), [])

# ── /api/companies carries a weekly count ──────────────────────────────────
cos = {c["id"]: c for c in client.get("/api/companies").json()}
check("news_7d", (cos[RL]["news_7d"], cos[PEL]["news_7d"], cos[AUTO]["news_7d"]), (2, 1, 0))

# ── brief section ──────────────────────────────────────────────────────────
from brief.generator import company_news_lines  # noqa: E402
with Session() as db:
    lines = company_news_lines(db)
check("brief: launches stay out, applied first", len(lines), 2)
check("brief: applied company first", lines[0].startswith("- **Peloton** (you applied) · layoffs:"), True)
check("brief: funding line", "**Rocket Lab** · funding: Rocket Lab raises $40M" in lines[1], True)

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all news API checks passed")
