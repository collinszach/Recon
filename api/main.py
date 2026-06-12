"""Recon API — REST endpoints + serves the dashboard and brief."""
import logging
from datetime import date
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from config import settings
from db import (
    Base, engine, SessionLocal, Company, Role, Application, ApplicationEvent,
    Contact, DailyBrief, ScanRun, PushSubscription,
)
from seed.companies import seed as seed_companies

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("recon.api")

app = FastAPI(title="Recon", version="1.0.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)   # safety net; init.sql does the real work
    added = seed_companies()
    log.info("startup: seeded %d new companies", added)


# ─── health ─────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "scoring_mode": settings.scoring_mode}


# ─── roles ──────────────────────────────────────────────────
@app.get("/api/roles")
def list_roles(tier: str | None = None, company: str | None = None,
               min_fit: float = 0.0, db: Session = Depends(get_db)):
    q = select(Role).where(Role.status.in_(["open", "changed"]))
    if min_fit:
        q = q.where(Role.fit_score >= min_fit)
    rows = db.scalars(q.order_by(Role.fit_score.desc().nullslast())).all()
    out = []
    for r in rows:
        co = r.company
        if company and co and company.lower() not in co.name.lower():
            continue
        if tier and co and co.tier != tier:
            continue
        out.append({
            "id": r.id, "company": co.name if co else None,
            "tier": co.tier if co else None, "title": r.title,
            "location": r.location, "url": r.url, "status": r.status,
            "fit_score": r.fit_score, "domain": r.domain,
            "why_fit": r.why_fit, "tc_estimate": r.tc_estimate,
            "is_product_pm": r.is_product_pm,
        })
    return out


# ─── applications (pipeline) ────────────────────────────────
class AppCreate(BaseModel):
    role_id: int | None = None
    company_name: str | None = None
    role_title: str | None = None
    role_url: str | None = None
    stage: str = "watching"


class AppUpdate(BaseModel):
    stage: str | None = None
    stage_note: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    notes: str | None = None
    outcome: str | None = None


@app.get("/api/applications")
def list_apps(stage: str | None = None, db: Session = Depends(get_db)):
    q = select(Application)
    if stage:
        q = q.where(Application.stage == stage)
    return [_app_dict(a) for a in db.scalars(q.order_by(Application.updated_at.desc())).all()]


@app.post("/api/applications")
def create_app(body: AppCreate, db: Session = Depends(get_db)):
    if body.role_id:
        r = db.get(Role, body.role_id)
        if not r:
            raise HTTPException(404, "role not found")
        a = Application(role_id=r.id,
                        company_name=r.company.name if r.company else None,
                        role_title=r.title, role_url=r.url, stage=body.stage)
    else:
        a = Application(company_name=body.company_name, role_title=body.role_title,
                        role_url=body.role_url, stage=body.stage)
    db.add(a)
    db.commit()
    return _app_dict(a)


@app.patch("/api/applications/{app_id}")
def update_app(app_id: int, body: AppUpdate, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "application not found")
    if body.stage and body.stage != a.stage:
        db.add(ApplicationEvent(application_id=a.id, from_stage=a.stage,
                                 to_stage=body.stage, note=body.stage_note))
        a.stage = body.stage
        if body.stage == "applied" and a.applied_at is None:
            from datetime import datetime, timezone
            a.applied_at = datetime.now(timezone.utc)
    for f in ("next_action", "notes", "outcome"):
        v = getattr(body, f)
        if v is not None:
            setattr(a, f, v)
    if body.next_action_due is not None:
        a.next_action_due = body.next_action_due
    db.commit()
    return _app_dict(a)


@app.get("/api/applications/{app_id}/events")
def list_app_events(app_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "application not found")
    rows = db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app_id)
        .order_by(ApplicationEvent.at)
    ).all()
    return [{"id": e.id, "from_stage": e.from_stage, "to_stage": e.to_stage,
             "note": e.note, "at": e.at.isoformat() if e.at else None} for e in rows]


def _app_dict(a: Application) -> dict:
    return {"id": a.id, "company_name": a.company_name, "role_title": a.role_title,
            "role_url": a.role_url, "stage": a.stage, "outcome": a.outcome,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            "next_action": a.next_action,
            "next_action_due": a.next_action_due.isoformat() if a.next_action_due else None,
            "notes": a.notes,
            "fit_score": a.role.fit_score if a.role else None}


# ─── contacts ────────────────────────────────────────────────
class ContactCreate(BaseModel):
    company_id: int | None = None
    name: str | None = None
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None
    warmth: str | None = None
    notes: str | None = None


class ContactUpdate(BaseModel):
    company_id: int | None = None
    name: str | None = None
    role: str | None = None
    email: str | None = None
    linkedin: str | None = None
    warmth: str | None = None
    notes: str | None = None


@app.get("/api/contacts")
def list_contacts(company_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Contact)
    if company_id:
        q = q.where(Contact.company_id == company_id)
    rows = db.scalars(q.order_by(Contact.created_at.desc())).all()
    return [_contact_dict(c) for c in rows]


@app.post("/api/contacts")
def create_contact(body: ContactCreate, db: Session = Depends(get_db)):
    c = Contact(**body.model_dump())
    db.add(c)
    db.commit()
    return _contact_dict(c)


@app.patch("/api/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactUpdate, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(404, "contact not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(c, f, v)
    db.commit()
    return _contact_dict(c)


def _contact_dict(c: Contact) -> dict:
    return {"id": c.id, "company_id": c.company_id, "name": c.name, "role": c.role,
            "email": c.email, "linkedin": c.linkedin, "warmth": c.warmth,
            "notes": c.notes,
            "created_at": c.created_at.isoformat() if c.created_at else None}


# ─── brief ──────────────────────────────────────────────────
@app.get("/api/brief")
def get_brief(d: date | None = None, db: Session = Depends(get_db)):
    target = d or date.today()
    b = db.scalar(select(DailyBrief).where(DailyBrief.brief_date == target))
    if not b:
        b = db.scalar(select(DailyBrief).order_by(DailyBrief.brief_date.desc()))
    if not b:
        return {"date": str(target), "markdown": "_No brief yet. Run a scan._"}
    return {"date": b.brief_date.isoformat(), "markdown": b.markdown,
            "new_count": b.new_count, "action_count": b.action_count}


# ─── manual scan trigger (also runs nightly via worker) ─────
@app.post("/api/scan/run")
def trigger_scan():
    from scan.runner import run_daily_scan
    return run_daily_scan()


@app.get("/api/scan/runs")
def scan_runs(db: Session = Depends(get_db)):
    rows = db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(30)).all()
    return [{"id": r.id, "started": r.started_at.isoformat(),
             "companies": r.companies_scanned, "new": r.new_count,
             "changed": r.changed_count, "closed": r.closed_count,
             "cost_usd": r.est_cost_usd, "errors": r.errors} for r in rows]


# ─── static: master dashboard at / ──────────────────────────
@app.get("/", response_class=HTMLResponse)
def dashboard():
    return FileResponse("web/dashboard.html")

app.mount("/web", StaticFiles(directory="web"), name="web")


# ════════════════════════════════════════════════════════════
# ─── web push: subscription + service worker (added by the   ─
# ─── notification-delivery feature; see api/notify/push.py)   ─
# ════════════════════════════════════════════════════════════
class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: dict


@app.post("/api/push/subscribe")
def push_subscribe(body: PushSubscriptionIn, db: Session = Depends(get_db)):
    p256dh = body.keys.get("p256dh")
    auth = body.keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(400, "subscription missing p256dh/auth keys")

    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.add(PushSubscription(endpoint=body.endpoint, p256dh=p256dh, auth=auth))
    db.commit()
    return {"status": "ok"}


@app.get("/api/push/vapid-public-key")
def push_vapid_public_key():
    return {"key": settings.vapid_public_key}


# service worker must be served from the site root to control the page
@app.get("/sw.js")
def service_worker():
    return FileResponse("web/sw.js", media_type="application/javascript")
