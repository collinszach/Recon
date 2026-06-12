"""Worker: runs the daily scan on a schedule. Lightweight for the N95."""
import logging
import sys
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# api package is mounted on PYTHONPATH via the image
sys.path.insert(0, "/app/api")

from config import settings          # noqa: E402
from scan.runner import run_daily_scan  # noqa: E402

logging.basicConfig(level=settings.log_level,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("recon.worker")


def job():
    log.info("daily scan starting")
    try:
        result = run_daily_scan()
        log.info("daily scan done: %s", result["totals"])
    except Exception:
        log.exception("daily scan failed")


def main():
    sched = BlockingScheduler(timezone=settings.tz)
    sched.add_job(job, CronTrigger(hour=settings.scan_hour_local, minute=0),
                  id="daily_scan", max_instances=1, coalesce=True)
    log.info("worker up — daily scan scheduled for %02d:00 %s",
             settings.scan_hour_local, settings.tz)
    # give the API a moment on cold start
    time.sleep(5)
    sched.start()


if __name__ == "__main__":
    main()
