"""Build and persist the daily Markdown brief."""
import logging
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session
from db import Role, Application, DailyBrief, Company, CompanyNews

log = logging.getLogger("recon.brief")


def company_news_lines(db: Session, hours: int = 48, max_lines: int = 8) -> list[str]:
    """One line per company with job-hunt-relevant news (funding, layoffs,
    freezes, M&A, leadership, hiring) in the last `hours`. Companies Zach has
    a live application with come first. Empty when there's nothing — the
    section is left out rather than padded."""
    from news.tagging import BRIEF_TAGS, TAG_ORDER
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.scalars(
        select(CompanyNews).join(Company).where(
            Company.dismissed_at.is_(None),
            CompanyNews.tags.isnot(None),
            func.coalesce(CompanyNews.published_at, CompanyNews.fetched_at) >= cutoff)
    ).all()
    live = set(db.scalars(
        select(Role.company_id).join(Application, Application.role_id == Role.id)
        .where(Application.stage != "closed")).all())

    def rank(n):
        tags = [t for t in n.tags.split(",") if t in BRIEF_TAGS]
        return min((TAG_ORDER.index(t) for t in tags), default=99)

    best: dict[int, CompanyNews] = {}
    for n in rows:
        if rank(n) == 99:
            continue
        cur = best.get(n.company_id)
        if cur is None or rank(n) < rank(cur):
            best[n.company_id] = n
    picked = sorted(best.values(), key=lambda n: (n.company_id not in live, rank(n)))[:max_lines]
    out = []
    for n in picked:
        tag = next(t for t in TAG_ORDER if t in n.tags.split(",") and t in BRIEF_TAGS)
        applied = " (you applied)" if n.company_id in live else ""
        src = f" — [{n.source}]({n.url})" if n.source else f" — [link]({n.url})"
        out.append(f"- **{n.company.name}**{applied} · {tag.replace('_', ' ')}: {n.title}{src}")
    return out


def build_brief(db: Session, today: date, totals: dict) -> DailyBrief:
    # roles worth attention: open/changed, fit >= 7, scored
    fresh = db.scalars(
        select(Role)
        .where(and_(Role.status.in_(["open", "changed"]),
                    Role.fit_score >= 7))
        .order_by(Role.fit_score.desc())
        .limit(25)
    ).all()

    # actions: stale applied cards or follow-ups due
    stale_cutoff = today - timedelta(days=10)
    actions = db.scalars(
        select(Application).where(
            and_(Application.stage == "applied",
                 Application.applied_at.isnot(None))
        )
    ).all()
    action_items = [a for a in actions
                    if a.applied_at and a.applied_at.date() <= stale_cutoff]
    due = db.scalars(
        select(Application).where(
            and_(Application.next_action_due.isnot(None),
                 Application.next_action_due <= today,
                 Application.stage != "closed")
        )
    ).all()

    # Headline counts scored roles per track, not the full-time firehose.
    interns = totals.get("interns")
    fulltime = totals.get("fulltime")
    parts = []
    if interns is not None: parts.append(f"{interns} internships")
    if fulltime is not None: parts.append(f"{fulltime} full-time PM")
    head_new = " · ".join(parts) if parts else f"{totals['new']} new"
    lines = [f"# Recon — {today.isoformat()}",
             f"**{head_new} · {totals['changed']} changed · "
             f"{len(action_items) + len(due)} need action**\n"]

    lines.append("## Needs your action")
    if not action_items and not due:
        lines.append("- Nothing overdue. Clean slate.")
    for a in due:
        lines.append(f"- ⏰ {a.company_name} — {a.role_title}: {a.next_action or 'follow up'} (due {a.next_action_due})")
    for a in action_items:
        lines.append(f"- 🕓 {a.company_name} — {a.role_title}: applied {a.applied_at.date()}, no movement in 10+ days")

    from scan.intern_filter import is_internship

    def _line(r):
        co = r.company.name if r.company else "?"
        tc = f" · {r.tc_estimate}" if r.tc_estimate else ""
        why = f" — {r.why_fit}" if r.why_fit else ""
        flag = "" if r.is_product_pm is not False else " ⚠️(program/PM check)"
        return f"- **{co}** {r.title} — fit {r.fit_score:.1f}{tc}{flag}{why}"

    interns_fresh = [r for r in fresh if is_internship(r.title, r.department)]
    ft_fresh = [r for r in fresh if not is_internship(r.title, r.department)]

    lines.append("\n## Summer 2027 internships worth your time")
    if not interns_fresh:
        lines.append("- No new high-fit internships today. (Most Summer 2027 reqs post Aug 2026–Jan 2027.)")
    for r in interns_fresh:
        lines.append(_line(r))

    lines.append("\n## Full-time product roles worth your time")
    if not ft_fresh:
        lines.append("- No new high-fit full-time product roles today.")
    for r in ft_fresh:
        lines.append(_line(r))

    try:
        news_lines = company_news_lines(db)
    except Exception as e:  # news is garnish; never cost Zach the brief
        db.rollback()
        log.warning("brief news section failed: %s: %s", type(e).__name__, e)
        news_lines = []
    if news_lines:
        lines.append("\n## Company news")
        lines += news_lines

    # pipeline snapshot
    lines.append("\n## Pipeline snapshot")
    snap = {}
    for a in db.scalars(select(Application)).all():
        snap[a.stage] = snap.get(a.stage, 0) + 1
    order = ["watching", "drafting", "applied", "screen", "onsite", "offer", "closed"]
    lines.append("- " + " · ".join(f"{s.capitalize()} {snap.get(s,0)}" for s in order))

    markdown = "\n".join(lines)
    action_count = len(action_items) + len(due)

    existing = db.scalar(select(DailyBrief).where(DailyBrief.brief_date == today))
    if existing:
        existing.markdown = markdown
        existing.new_count = totals["new"]
        existing.action_count = action_count
        brief = existing
    else:
        brief = DailyBrief(brief_date=today, markdown=markdown,
                           new_count=totals["new"], action_count=action_count)
        db.add(brief)
    db.commit()
    return brief
