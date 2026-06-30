"""Diff freshly-fetched roles against DB state for one company."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from db import Role
from parsers import NormalizedRole
from scan.geo import metro_of


def reconcile_company(db: Session, company_id: int, fetched: list[NormalizedRole]) -> dict:
    """Returns counts and lists of new / changed role ids."""
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
                remote_flag=f.remote_flag,
                department=f.department,
                url=f.url,
                description=f.description or None,
                description_hash=f.description_hash,
                posted_at=f.posted_at,
                status="open",
            )
            db.add(role)
            db.flush()
            new_ids.append(role.id)
        else:
            if row.description_hash != f.description_hash:
                row.title = f.title
                row.location = f.location
                row.metro = metro_of(f.location)
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
                row.status = "open"
            row.last_seen = now

    # anything in DB but no longer present = closed
    closed = 0
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
