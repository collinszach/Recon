"""Full daily scan: fetch every active company, reconcile, score, brief."""
import logging
from datetime import datetime, timezone, date
from sqlalchemy import select
from sqlalchemy.orm import Session
from config import settings
from db import SessionLocal, Company, Role, ScanRun
from parsers import get_parser
from scan.reconcile import reconcile_company
from scan.intern_filter import filter_internships, filter_fulltime_pm
from scoring.claude_scorer import score_roles
from brief.generator import build_brief

log = logging.getLogger("recon.scan")


def run_daily_scan() -> dict:
    db: Session = SessionLocal()
    run = ScanRun(started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()

    totals = {"new": 0, "changed": 0, "closed": 0, "companies": 0}
    errors: list[str] = []
    fresh_role_ids: list[int] = []
    today = date.today()

    try:
        companies = db.scalars(select(Company)).all()
        for co in companies:
            if co.snoozed_until and co.snoozed_until >= today:
                continue
            parser = get_parser(co.ats_name or "")
            if parser is None:
                continue  # manual / workday handled elsewhere
            try:
                fetched = parser.fetch(co.ats_token)
                result = reconcile_company(db, co.id, fetched)
                totals["new"] += result["new"]
                totals["changed"] += result["changed"]
                totals["closed"] += result["closed"]
                totals["companies"] += 1
                fresh_role_ids += result["new_ids"] + result["changed_ids"]
                log.info("scanned %s: +%d ~%d -%d",
                         co.name, result["new"], result["changed"], result["closed"])
            except Exception as e:  # one company failing must not kill the run
                msg = f"{co.name}: {type(e).__name__}: {e}"
                errors.append(msg)
                log.warning("scan error %s", msg)

        # score only the new + changed roles, narrowed to the tracks we care about
        # (internships and/or full-time product-management roles). Everything else
        # stays in the DB unscored — keeps the feed and the API bill focused.
        score_cost = {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}
        if fresh_role_ids:
            fresh = db.scalars(select(Role).where(Role.id.in_(fresh_role_ids))).all()
            mode = "intern" if settings.intern_only else settings.track_mode
            tier_rank = {"A": 0, "B": 1, "C": 2}
            to_score: list[Role] = []

            if mode in ("intern", "both"):
                interns = filter_internships(fresh)[: settings.score_max_intern]
                to_score += interns
                totals["interns"] = len(interns)

            if mode in ("fulltime", "both"):
                ft = filter_fulltime_pm(fresh)
                # target-tier companies first, so the cap keeps the best roles
                ft.sort(key=lambda r: tier_rank.get(r.company.tier if r.company else "C", 3))
                ft = ft[: settings.score_max_fulltime]
                to_score += ft
                totals["fulltime"] = len(ft)

            log.info("track filter (%s): %d internships + %d full-time PM of %d new/changed",
                     mode, totals.get("interns", 0), totals.get("fulltime", 0), len(fresh))
            if to_score:
                score_cost = score_roles(db, to_score)

        # build + persist today's brief
        brief = build_brief(db, today, totals)

        # deliver the brief over push / email / gdoc — never let this kill the run
        try:
            from notify.deliver import deliver_brief
            delivery = deliver_brief(brief)
            log.info("brief delivery: %s", delivery)
        except Exception as e:
            log.warning("brief delivery failed: %s: %s", type(e).__name__, e)

        run.finished_at = datetime.now(timezone.utc)
        run.companies_scanned = totals["companies"]
        run.new_count = totals["new"]
        run.changed_count = totals["changed"]
        run.closed_count = totals["closed"]
        run.claude_tokens_in = score_cost["tokens_in"]
        run.claude_tokens_out = score_cost["tokens_out"]
        run.est_cost_usd = score_cost["usd"]
        run.errors = "\n".join(errors) if errors else None
        db.commit()

        log.info("scan complete: %s  cost=$%.3f", totals, score_cost["usd"])
        return {"totals": totals, "cost": score_cost, "brief_date": str(today),
                "errors": errors}
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run_daily_scan())
