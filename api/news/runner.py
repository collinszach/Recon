"""Daily company-news fetch: pick companies, query the provider, keep what is
really about the company, dedupe, tag, store.

Runs from the worker (worker/scheduler.py news_job) and POST /api/news/run.
Gated to once per NEWS_INTERVAL_HOURS by the last successful JobRun(kind=news),
so a worker restart does not spend a second day's quota. Every company is
wrapped on its own: one bad query must never end the run.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete, or_
from sqlalchemy.orm import Session

from config import settings
from db import Application, Company, CompanyNews, JobRun, Role
from news import tagging
from news.registry import active_provider

log = logging.getLogger("recon.news")

# Companies auto-created by the job-search aggregators: one per employer that
# ever posted a matching role, thousands of them. "Tracked" means the curated
# list, plus anyone Zach has an application with.
_SEARCH_PROVIDERS = {"jsearch", "usajobs", "themuse", "adzuna"}


def tracked_companies(db: Session) -> list[Company]:
    applied = select(Role.company_id).join(Application, Application.role_id == Role.id)
    return db.scalars(
        select(Company).where(
            Company.dismissed_at.is_(None),
            or_(Company.ats_name.is_(None),
                Company.ats_name.notin_(_SEARCH_PROVIDERS),
                Company.id.in_(applied)))
    ).all()


def _priority(db: Session, companies: list[Company]) -> list[Company]:
    """Companies with a live application first, then never-checked, then the
    least recently checked, tier A before B before C within each."""
    live = set(db.scalars(
        select(Role.company_id).join(Application, Application.role_id == Role.id)
        .where(Application.stage != "closed")).all())
    rank = {"A": 0, "B": 1, "C": 2}
    return sorted(companies, key=lambda c: (
        c.id not in live,
        _aware(c.news_checked_at),
        rank.get(c.tier or "", 3),
    ))


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def due(db: Session) -> bool:
    last = db.scalar(select(JobRun.started_at).where(
        JobRun.kind == "news", JobRun.status == "ok").order_by(JobRun.started_at.desc()))
    if last is None:
        return True
    return datetime.now(timezone.utc) - _aware(last) >= timedelta(hours=settings.news_interval_hours)


def store_articles(db: Session, company: Company, phrases: list[str], articles, provider: str) -> int:
    """Insert the articles that name the company and aren't already stored
    (same URL, or same headline syndicated elsewhere). Returns rows added."""
    existing = db.execute(select(CompanyNews.url_key, CompanyNews.title_key)
                          .where(CompanyNews.company_id == company.id)).all()
    seen_urls = {u for u, _ in existing}
    seen_titles = {t for _, t in existing}
    added = 0
    for a in articles:
        if not tagging.mentions(phrases, a.title, a.description):
            continue
        uk, tk = tagging.url_key(a.url), tagging.title_key(a.title)
        if not uk or uk in seen_urls or (tk and tk in seen_titles):
            continue
        seen_urls.add(uk)
        seen_titles.add(tk)
        db.add(CompanyNews(
            company_id=company.id, title=a.title[:1000], url=a.url, url_key=uk,
            title_key=tk, source=a.source, description=a.description,
            published_at=a.published_at, provider=provider,
            tags=",".join(tagging.tag(a.title, a.description)) or None,
        ))
        added += 1
    return added


def run_news_fetch(db: Session, force: bool = False, limit: int | None = None) -> dict:
    if not settings.news_enabled:
        return {"status": "off"}
    if not force and not due(db):
        return {"status": "skipped", "reason": "fetched within the last "
                f"{settings.news_interval_hours}h"}
    provider = active_provider()
    if provider is None:
        return {"status": "off", "reason": f"news provider {settings.news_provider!r} not configured"}

    run = JobRun(kind="news", started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()

    cap = limit or settings.news_max_companies_per_run or provider.daily_budget
    queue = _priority(db, tracked_companies(db))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=settings.news_lookback_days)
    checked = added = 0
    errors: list[str] = []
    for co in queue:
        if checked >= cap:
            break
        phrases = tagging.phrases_for(co.name)
        if not phrases:
            continue
        if checked:
            time.sleep(provider.min_interval_sec)
        checked += 1
        try:
            n = store_articles(db, co, phrases, provider.fetch(phrases, since), provider.name)
            co.news_checked_at = now
            db.commit()
            added += n
            if n:
                log.info("news %s: +%d", co.name, n)
        except Exception as e:  # one company failing must not kill the run
            db.rollback()
            errors.append(f"{co.name}: {type(e).__name__}: {e}"[:300])
            log.warning("news error %s: %s", co.name, e)
            # A quota/auth failure will fail every remaining company the same way.
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (401, 403, 429):
                break

    pruned = db.execute(delete(CompanyNews).where(
        CompanyNews.fetched_at < now - timedelta(days=settings.news_retention_days))).rowcount

    run.finished_at = datetime.now(timezone.utc)
    # Every query failing is an error; some failing is a partial success.
    run.status = "error" if errors and len(errors) >= checked else "ok"
    run.summary = (f"{added} new articles from {checked} companies via {provider.name}"
                   + (f", {len(errors)} errors" if errors else ""))
    run.detail = json.dumps({"errors": errors[:20], "pruned": pruned, "queue": len(queue)})
    db.commit()
    log.info("news fetch: %s", run.summary)
    return {"status": run.status, "provider": provider.name, "companies_checked": checked,
            "added": added, "errors": errors, "pruned": pruned, "tracked": len(queue)}
