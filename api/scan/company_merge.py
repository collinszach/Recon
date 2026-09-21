"""Fold aggregator-invented shadow companies into the real ones.

Aggregators file roles under whatever employer string the posting carried, so
the DB grows a second company for an employer Recon already pulls directly:
"Anduril Industries" beside "Anduril", "Amazon Development Center U.S., Inc."
beside "Amazon", "Micron Technology" beside "Micron". Those shadows hold a
sampled slice of the same board, under a name that looks like a different
employer in the feed.

Merging reassigns the shadow's roles to the canonical company and deletes the
shadow. Roles that collide on the (company_id, ats_job_id) unique constraint
are dropped rather than reassigned — a collision means the canonical company
already has that exact posting from its own board, which is the better copy.

Applications and materials point at roles by id, not at companies, so a merge
never disturbs anything Zach has tracked.
"""
from __future__ import annotations
import logging
import re

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db import Company, Role

log = logging.getLogger("recon.company_merge")

AGGREGATOR = ("adzuna", "jsearch", "jsearch_company", "themuse", "usajobs")

# Corporate-entity noise that turns a real company name into a distinct one.
_NOISE_RE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|company|holdings|group|plc|"
    r"technologies|technology|industries|services|solutions|systems|"
    # Punctuation is stripped before this runs, so "U.S." arrives as "u s" —
    # matching on "u\.s\." alone left "Amazon Development Center U.S., Inc."
    # keying as "amazonus" and missing its merge.
    r"development\s+center|data\s+services|usa|u\s+s|us|university\s+recruitment|"
    r"recruitment|careers|global|international)\b", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def canonical_key(name: str) -> str:
    """"Anduril Industries" -> "anduril"; "Amazon Data Services, Inc." -> "amazon"."""
    s = _PUNCT_RE.sub(" ", (name or "").lower())
    s = _NOISE_RE.sub(" ", s)
    return _PUNCT_RE.sub("", s)


def find_shadows(db: Session) -> list[tuple[Company, Company]]:
    """(shadow, canonical) pairs: an aggregator company whose canonical key
    matches a company that has a real board configured.

    Only ever merges *into* a directly-pulled company. Two aggregator companies
    that reduce to the same key are left alone — without a board there's no
    reason to prefer either, and picking one would be a coin flip.
    """
    everyone = db.scalars(select(Company)).all()
    direct = {}
    for c in everyone:
        if c.ats_name and c.ats_name.lower() not in AGGREGATOR:
            direct.setdefault(canonical_key(c.name), c)

    pairs: list[tuple[Company, Company]] = []
    for c in everyone:
        if not c.ats_name or c.ats_name.lower() not in AGGREGATOR:
            continue
        key = canonical_key(c.name)
        target = direct.get(key)
        if target and target.id != c.id and key:
            pairs.append((c, target))
    return pairs


def merge(db: Session, dry_run: bool = True) -> dict:
    """Reassign each shadow's roles to its canonical company, then delete it."""
    pairs = find_shadows(db)
    out = []
    for shadow, target in pairs:
        existing = {
            jid for (jid,) in db.execute(
                select(Role.ats_job_id).where(Role.company_id == target.id)).all()
        }
        roles = db.scalars(select(Role).where(Role.company_id == shadow.id)).all()
        moved = dropped = 0
        for r in roles:
            if r.ats_job_id in existing:
                dropped += 1                    # canonical already has this posting
                if not dry_run:
                    db.delete(r)
            else:
                moved += 1
                existing.add(r.ats_job_id)
                if not dry_run:
                    r.company_id = target.id
        out.append({"shadow": shadow.name, "into": target.name,
                    "ats": target.ats_name, "moved": moved, "dropped": dropped})
        if not dry_run:
            db.flush()
            db.delete(shadow)
    if not dry_run:
        db.commit()
        log.info("company merge: %d shadows folded in", len(out))
    else:
        db.rollback()
    return {"dry_run": dry_run, "merged": len(out), "details": out}
