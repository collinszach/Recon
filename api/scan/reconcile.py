"""Diff freshly-fetched roles against DB state for one company."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from db import Role
from parsers import NormalizedRole
from scan.geo import metro_of, states_csv


def reconcile_company(db: Session, company_id: int, fetched: list[NormalizedRole],
                      close_missing: bool = True, backfill: bool = False) -> dict:
    """Returns counts and lists of new / changed role ids. When close_missing is
    False the caller's fetch is a sampled slice (not the full board), so roles
    absent from `fetched` are left as-is rather than marked closed.

    `backfill` marks everything inserted as the board's back catalogue rather
    than new postings — true only on a company's first-ever scan, where every
    posting arrives at once with first_seen=now regardless of its real age."""
    existing = {
        r.ats_job_id: r
        for r in db.scalars(select(Role).where(Role.company_id == company_id))
    }
    fetched_ids = {f.ats_job_id for f in fetched}
    now = datetime.now(timezone.utc)

    new_ids, changed_ids = [], []

    for f in fetched:
        row = existing.get(f.ats_job_id)
        if row is None:
            role = Role(
                company_id=company_id,
                ats_job_id=f.ats_job_id,
                title=f.title,
                location=f.location,
                metro=metro_of(f.location),
                state=states_csv(f.location),
                remote_flag=f.remote_flag,
                department=f.department,
                url=f.url,
                description=f.description or None,
                description_hash=f.description_hash,
                posted_at=f.posted_at,
                status="open",
                is_backfill=backfill,
            )
            db.add(role)
            db.flush()
            new_ids.append(role.id)
        else:
            if row.description_hash != f.description_hash:
                row.title = f.title
                row.location = f.location
                row.metro = metro_of(f.location)
                row.state = states_csv(f.location)
                row.department = f.department
                row.url = f.url
                row.description = f.description or None
                row.description_hash = f.description_hash
                if f.posted_at:
                    row.posted_at = f.posted_at
                row.status = "changed"
                row.scored_at = None          # force re-score
                changed_ids.append(row.id)
            else:
                # Opportunistic backfill: rows created before we stored the JD
                # have description=NULL. Fill it on an unchanged re-fetch without
                # forcing a re-score (the hash, hence the scoring inputs, matched).
                if not row.description and f.description:
                    row.description = f.description
                # Same for the posting date. Workday's relative `postedOn` only
                # started being parsed on 2026-09-21, so every row ingested
                # before that has posted_at=NULL and would keep it until the
                # posting's text happened to change — which for most postings is
                # never. Without this the dashboard reads them as undated
                # forever and "posted today" stays wrong for the boards that
                # matter most.
                if not row.posted_at and f.posted_at:
                    row.posted_at = f.posted_at
                row.status = "open"
            row.last_seen = now

    # anything in DB but no longer present = closed (only for an authoritative
    # full-board fetch; a sampled fetch must not close roles it merely omitted)
    closed = 0
    if close_missing:
        for ats_id, row in existing.items():
            if ats_id not in fetched_ids and row.status != "closed":
                row.status = "closed"
                closed += 1

    db.commit()
    return {
        "new_ids": new_ids,
        "changed_ids": changed_ids,
        "new": len(new_ids),
        "changed": len(changed_ids),
        "closed": closed,
    }
