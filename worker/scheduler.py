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
    log.info("worker up — scan scheduled every %d hour(s) (%s); first run ~15s after startup",
             hours, settings.tz)
    sched.start()


if __name__ == "__main__":
    main()
