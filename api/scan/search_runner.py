"""Ingest roles from third-party search providers (JSearch, USAJobs).

Search returns roles from MANY employers for a keyword query, so this runs
outside the per-company ATS loop:
  1. geo-filter results to Zach's target metros (search is wide),
  2. upsert a Company per employer (auto-discovery of new employers),
  3. dedupe against roles already in that company (ATS-sourced wins),
  4. INSERT new roles only — never 'close' roles a query happened to omit, since
     a search result set is a sampled slice, not an authoritative board.

Returns {new_ids, ...} like reconcile_company so the caller can score the new
roles on the existing track/scoring path.
"""
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from db import Company, Role
from scan.geo import metro_of
from search import default_terms, enabled_providers

log = logging.getLogger("recon.search")

_SUFFIX = re.compile(r"[,.]?\s*(inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|"
                     r"co|company|gmbh|plc|holdings|group)\.?$", re.IGNORECASE)


def _norm_company(name: str) -> str:
    s = re.sub(r"\s+", " ", name or "").strip()
    s = _SUFFIX.sub("", s).strip()
    return s or (name or "").strip()


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (t or "").lower())).strip()


def run_search(db: Session) -> dict:
    providers = enabled_providers()
    if not providers:
        return {"new_ids": [], "new": 0, "providers": 0, "results": 0,
                "new_companies": 0, "errors": []}

    terms = default_terms()
    # Interleave term-first so the cap trims whole low-priority terms rather than
    # starving the second provider (USAJobs) of every query.
    queries = [(p, t) for t in terms for p in providers][: settings.search_max_queries_per_run]

    # company lookup cache, keyed by normalized name (case-insensitive)
    companies = {_norm_company(c.name).lower(): c for c in db.scalars(select(Company)).all()}
    # per-company set of normalized open-role titles, lazily filled for dedupe
    titles_by_company: dict[int, set[str]] = {}

    def _open_titles(company_id: int) -> set[str]:
        if company_id not in titles_by_company:
            titles_by_company[company_id] = {
                _norm_title(x.title)
                for x in db.scalars(select(Role).where(
                    Role.company_id == company_id, Role.status != "closed"))
            }
        return titles_by_company[company_id]

    now = datetime.now(timezone.utc)
    new_ids: list[int] = []
    errors: list[str] = []
    new_companies = 0
    results_total = 0
    # per-provider tally so a whole provider silently failing (e.g. a lapsed
    # RapidAPI subscription -> every JSearch call 404s) gets surfaced loudly
    # below instead of hiding behind the per-query try/except.
    prov_stats: dict[str, dict[str, int]] = {
        p.name: {"queries": 0, "results": 0, "errors": 0} for p in providers}

    for provider, term in queries:
        prov_stats[provider.name]["queries"] += 1
        try:
            results = provider.search(term)
        except Exception as e:  # one query failing must not kill the run
            msg = f"{provider.name}/{term!r}: {type(e).__name__}: {e}"
            errors.append(msg)
            prov_stats[provider.name]["errors"] += 1
            log.warning("search error %s", msg)
            continue

        prov_stats[provider.name]["results"] += len(results)
        for sr in results:
            results_total += 1
            r = sr.role
            metro = metro_of(r.location)
            if settings.search_metros_only and not metro:
                continue                       # keep search tightly geo-relevant

            key = _norm_company(sr.employer).lower()
            co = companies.get(key)
            if co is None:
                co = Company(name=sr.employer.strip(), tier="B", ats_name=provider.name,
                             notes=f"auto-added via {provider.name} search {now.date()}")
                db.add(co)
                db.flush()                     # assign co.id
                companies[key] = co
                titles_by_company[co.id] = set()
                new_companies += 1

            ntitle = _norm_title(r.title)
            seen = _open_titles(co.id)
            if ntitle in seen:                 # already have this role (likely from its ATS)
                continue

            role = Role(
                company_id=co.id, ats_job_id=r.ats_job_id, source=provider.name,
                title=r.title, location=r.location, metro=metro,
                remote_flag=r.remote_flag, department=r.department, url=r.url,
                description_hash=r.description_hash, posted_at=r.posted_at, status="open",
            )
            db.add(role)
            db.flush()
            seen.add(ntitle)
            new_ids.append(role.id)

    # Surface a provider that's wholly down (every query errored, zero results) —
    # the usual signal is a lapsed/expired RapidAPI subscription. This is otherwise
    # invisible because the per-query except only logs individual failures.
    for pname, s in prov_stats.items():
        if s["queries"] and s["results"] == 0 and s["errors"] == s["queries"]:
            log.error("search provider %r returned nothing: all %d queries failed "
                      "(check API key / subscription)", pname, s["queries"])
            errors.append(f"{pname}: all {s['queries']} queries failed — provider likely down")

    # ── company sweep: proprietary/bot-walled employers with no public ATS board ──
    # These are seeded ats_name='jsearch_company' and skipped by the per-company ATS
    # loop (no parser). One employer-scoped JSearch query each pulls their roles in.
    # Capped per run and round-robined by day so the whole set is covered across a
    # cycle without blowing the free tier. Hits are pinned to the known Company.
    swept = 0
    # prefer a working company-search provider; Muse (free) over JSearch (which
    # 404s /search on the current plan). Any provider exposing search_company works.
    _order = {"themuse": 0, "jsearch": 1}
    js = next((p for p in sorted(providers, key=lambda p: _order.get(p.name, 9))
               if hasattr(p, "search_company")), None)
    sweep_all = sorted((c for c in companies.values()
                        if (c.ats_name or "") == "jsearch_company"), key=lambda c: c.id)
    cap = settings.search_company_sweep_max
    if js and sweep_all and cap > 0:
        n = len(sweep_all)
        start = (now.timetuple().tm_yday * cap) % n     # deterministic daily rotation
        todays = [sweep_all[(start + i) % n] for i in range(min(cap, n))]
        for co in todays:
            swept += 1
            try:
                results = js.search_company(co.name)
            except Exception as e:
                msg = f"jsearch/company {co.name!r}: {type(e).__name__}: {e}"
                errors.append(msg)
                log.warning("search error %s", msg)
                continue
            ckey = _norm_company(co.name).lower()
            for sr in results:
                results_total += 1
                r = sr.role
                metro = metro_of(r.location)
                if settings.search_metros_only and not metro:
                    continue
                ekey = _norm_company(sr.employer).lower()
                if ckey not in ekey and ekey not in ckey:
                    continue                   # employer-pin guard: not this company
                ntitle = _norm_title(r.title)
                seen = _open_titles(co.id)
                if ntitle in seen:
                    continue
                role = Role(
                    company_id=co.id, ats_job_id=r.ats_job_id, source="jsearch",
                    title=r.title, location=r.location, metro=metro,
                    remote_flag=r.remote_flag, department=r.department, url=r.url,
                    description_hash=r.description_hash, posted_at=r.posted_at, status="open",
                )
                db.add(role)
                db.flush()
                seen.add(ntitle)
                new_ids.append(role.id)

    db.commit()
    log.info("search: %d providers x %d terms (%d queries) + %d company sweeps, "
             "%d results -> +%d roles, +%d companies",
             len(providers), len(terms), len(queries), swept, results_total,
             len(new_ids), new_companies)
    return {"new_ids": new_ids, "new": len(new_ids), "providers": len(providers),
            "results": results_total, "new_companies": new_companies,
            "swept": swept, "errors": errors}
