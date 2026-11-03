"""Worker: runs the daily scan on a schedule. Lightweight for the N95."""
import logging
import sys
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

# api package is mounted on PYTHONPATH via the image
sys.path.insert(0, "/app/api")

from config import settings          # noqa: E402
from scan.runner import run_daily_scan  # noqa: E402

logging.basicConfig(level=settings.log_level,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("recon.worker")


def job():
    log.info("scan starting")
    try:
        result = run_daily_scan()
        log.info("scan done: %s", result["totals"])
    except Exception:
        log.exception("scan failed")


def discovery_job():
    """Weekly startup discovery — proposes + adds new startups with writeups
    and contacts (2026-08-15, Zach's call: ongoing discovery, not one-time).
    AI cost, unlike the scan job, so this stays weekly not hourly."""
    log.info("startup discovery starting")
    from db import SessionLocal
    from startups.researcher import run_discovery
    db = SessionLocal()
    try:
        result = run_discovery(db, n=settings.startup_discovery_batch)
        log.info("startup discovery done: +%d added, %d skipped",
                 len(result["added"]), len(result["skipped"]))
    except Exception:
        log.exception("startup discovery failed")
    finally:
        db.close()


def news_job():
    """Daily company news. Checked hourly but gated inside run_news_fetch to
    once per NEWS_INTERVAL_HOURS (last successful run in job_runs), so a
    restart never spends a second day's provider quota."""
    from db import SessionLocal
    from news.runner import run_news_fetch
    db = SessionLocal()
    try:
        result = run_news_fetch(db)
        if result.get("status") != "skipped":
            log.info("news: %s", {k: v for k, v in result.items() if k != "errors"})
    except Exception:
        log.exception("news fetch failed")
    finally:
        db.close()


def main():
    sched = BlockingScheduler(timezone=settings.tz)
    hours = max(1, settings.scan_interval_hours)
    # recurring scan every N hours
    sched.add_job(job, IntervalTrigger(hours=hours, timezone=settings.tz),
                  id="interval_scan", max_instances=1, coalesce=True)
    # also kick one off shortly after startup (give the API a moment on cold start)
    sched.add_job(job, "date",
                  run_date=datetime.now() + timedelta(seconds=15),
                  id="startup_scan", max_instances=1, coalesce=True)
    # weekly startup discovery (separate from the job scan above)
    if settings.startup_discovery_enabled:
        sched.add_job(discovery_job, IntervalTrigger(weeks=1, timezone=settings.tz),
                      id="weekly_startup_discovery", max_instances=1, coalesce=True)
    # company news: hourly check, daily fetch (see news_job). First check runs
    # after the startup scan has had its head start.
    if settings.news_enabled:
        sched.add_job(news_job, IntervalTrigger(hours=1, timezone=settings.tz),
                      next_run_time=datetime.now() + timedelta(minutes=2),
                      id="daily_news", max_instances=1, coalesce=True)
    log.info("worker up — scan scheduled every %d hour(s) (%s); first run ~15s after startup; "
             "startup discovery %s; company news %s",
             hours, settings.tz, "weekly" if settings.startup_discovery_enabled else "disabled",
             f"every {settings.news_interval_hours}h" if settings.news_enabled else "disabled")
    sched.start()


if __name__ == "__main__":
    main()
