"""Full daily scan: fetch every active company, reconcile, score, brief."""
import logging
from datetime import datetime, timezone, date, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from config import settings
from db import SessionLocal, Company, Role, ScanRun
from parsers import get_parser
from scan.reconcile import reconcile_company
from scan.intern_filter import filter_internships, filter_fulltime_pm, filter_ops_strategy
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
    new_role_ids: list[int] = []          # genuinely new postings (for alerts)
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
                new_role_ids += result["new_ids"]
                log.info("scanned %s: +%d ~%d -%d",
                         co.name, result["new"], result["changed"], result["closed"])
            except Exception as e:  # one company failing must not kill the run
                msg = f"{co.name}: {type(e).__name__}: {e}"
                errors.append(msg)
                log.warning("scan error %s", msg)

        # ── third-party search sources (JSearch / USAJobs), gated to once/day ──
        # Scans run every few hours; search providers have free-tier quotas, so we
        # only hit them if no recent run already did. Search-found roles feed the
        # same track/scoring path below.
        if settings.search_enabled:
            now = datetime.now(timezone.utc)
            last = db.scalar(select(func.max(ScanRun.started_at)).where(ScanRun.searched.is_(True)))
            due = last is None or (now - last) >= timedelta(hours=settings.search_interval_hours)
            if due:
                try:
                    from scan.search_runner import run_search
                    sres = run_search(db)
                    fresh_role_ids += sres["new_ids"]
                    new_role_ids += sres["new_ids"]
                    totals["search_new"] = sres["new"]
                    totals["search_companies"] = sres["new_companies"]
                    errors += sres["errors"]
                    run.searched = True
                    db.commit()
                    log.info("search ingest: +%d roles, +%d companies (%d results)",
                             sres["new"], sres["new_companies"], sres["results"])
                except Exception as e:  # search must never kill the ATS scan
                    log.warning("search ingest failed: %s: %s", type(e).__name__, e)

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

            if mode in ("ops", "both"):
                ops = filter_ops_strategy(fresh)
                ops.sort(key=lambda r: tier_rank.get(r.company.tier if r.company else "C", 3))
                ops = ops[: settings.score_max_ops]
                to_score += ops
                totals["ops"] = len(ops)

            # Metro lane: any fresh role in one of Zach's target metros gets scored
            # even if a per-track cap would have cut it — geography is a first-class
            # signal. Includes (a) ATS roles that fit a track, AND (b) ALL search-
            # sourced roles (JSearch/USAJobs): they're cross-employer and already
            # geo-filtered at ingest, and their titles (esp. federal) often don't
            # match the PM/intern/ops classifiers, so we score them on merit rather
            # than drop them. Deduped against the track lanes above.
            from scan.intern_filter import is_fulltime_pm, is_internship, is_ops_strategy
            picked = {r.id for r in to_score}
            def _in_a_track(r) -> bool:
                if mode in ("intern", "both") and is_internship(r.title, r.department):
                    return True
                if mode in ("fulltime", "both") and is_fulltime_pm(r.title, r.department):
                    return True
                if mode in ("ops", "both") and is_ops_strategy(r.title, r.department):
                    return True
                return False
            metro_roles = [r for r in fresh
                           if r.metro and r.id not in picked
                           and (_in_a_track(r) or (r.source or "ats") != "ats")]
            metro_roles = metro_roles[: settings.score_max_metro]
            to_score += metro_roles
            totals["metro"] = len(metro_roles)

            log.info("track filter (%s): %d internships + %d full-time PM + %d ops/strategy "
                     "+ %d target-metro (uncapped) of %d new/changed",
                     mode, totals.get("interns", 0), totals.get("fulltime", 0),
                     totals.get("ops", 0), totals.get("metro", 0), len(fresh))
            if to_score:
                score_cost = score_roles(db, to_score)

            # alert on NEW postings that scored high (skip pass/low). Channels
            # no-op when disabled, so this is safe to always call.
            new_set = set(new_role_ids)
            alert_roles = [r for r in to_score
                           if r.id in new_set
                           and (r.fit_score or 0) >= settings.notify_min_fit
                           and (r.score_tier or "").upper() != "PASS"]
            if alert_roles:
                try:
                    from notify.deliver import deliver_alert
                    log.info("new-role alert: %s", deliver_alert(alert_roles))
                except Exception as e:
                    log.warning("alert failed: %s: %s", type(e).__name__, e)

        # build + persist today's brief
        brief = build_brief(db, today, totals)

        # deliver the brief over push / email / gdoc — never let this kill the run
        try:
            from notify.deliver import deliver_brief
            delivery = deliver_brief(brief)
            log.info("brief delivery: %s", delivery)
        except Exception as e:
            log.warning("brief delivery failed: %s: %s", type(e).__name__, e)

        # once-a-day pipeline reminders (follow-ups due, applied gone stale)
        try:
            if not brief.reminders_sent:
                from notify.deliver import deliver_reminders
                from db import Application, Interview
                apps = db.scalars(select(Application).where(Application.stage != "closed")).all()
                due = [a for a in apps if a.next_action_due and a.next_action_due <= today]
                stale = [a for a in apps if a.stage == "applied" and a.applied_at
                         and a.applied_at.date() <= today - timedelta(days=10)]
                ivs = db.scalars(select(Interview).where(
                    Interview.scheduled_at.isnot(None),
                    Interview.scheduled_at >= today,
                    Interview.scheduled_at <= today + timedelta(days=2))).all()
                if due or stale or ivs:
                    log.info("reminders: %s", deliver_reminders(due, stale, ivs))
                brief.reminders_sent = True
                db.commit()
        except Exception as e:
            log.warning("reminders failed: %s: %s", type(e).__name__, e)

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
