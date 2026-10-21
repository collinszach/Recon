"""When should Zach expect to hear back on an application?

Pure stdlib, so CI can test it without installing anything.

These are estimates, and each one says how it was reached. The one hard anchor
is the MBA recruiting calendar: Berkeley Haas's 2026-27 calendar runs
internship company events Oct 26 - Nov 19, 2026 and school-managed interviews
Jan 19 - Feb 18, 2027 (other schools are similar — Wharton allows first-year
interviews from early January, Kellogg's rounds run Jan 11 - Feb 2). MBA
programs hire on that calendar, so silence on an MBA application in October is
normal, not a bad sign. Everything else is ordinary hiring-pipeline pacing and
is labelled as a rule of thumb.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

MBA_FIRST_WORD = date(2026, 11, 15)   # just before Haas internship events close
MBA_INTERVIEWS_END = date(2027, 2, 18)

_MBA = re.compile(r"\bMBA\b|graduate\s+internship|campus\s+graduate\s+masters|"
                  r"leadership\s+accelerator|fellowship", re.I)
_OFF_CYCLE = re.compile(r"\b(fall|winter|spring)\s+20(26|27)\b|\bco-?op\b", re.I)

# Employers big enough to run a structured intern program on a slower clock
# than a startup's rolling hiring.
LARGE = {
    "adobe", "amazon", "amd", "amex", "americanexpress", "appian", "atlassian",
    "c3ai", "capitalone", "databricks", "doordash", "duolingo", "garmin",
    "garmininternationalinc", "generalmotors", "gevernova", "google",
    "hewlettpackardenterprise", "intuit", "marriott", "mastercard", "medline",
    "microsoft", "nike", "nvidia", "qualcomm", "sharkninja", "tiktok", "visa",
    "waymo", "zipline", "skydio",
}


def _sq(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def classify(title: str | None, company: str | None) -> str:
    """mba_cycle | off_cycle | structured | rolling."""
    t = title or ""
    if _MBA.search(t):
        return "mba_cycle"
    if _OFF_CYCLE.search(t):
        return "off_cycle"
    return "structured" if _sq(company) in LARGE else "rolling"


def expect(title: str | None, company: str | None, stage: str | None,
           applied: date | None, last_contact: date | None,
           today: date | None = None) -> dict | None:
    """{kind, label, from, to, state, why} or None when there's nothing to wait on.

    state: early (before the window), window, overdue (past it — follow up),
    likely_no (well past it for rolling hiring, where silence is the answer).
    """
    today = today or date.today()
    if stage in (None, "watching", "drafting", "closed", "offer"):
        return None
    if stage in ("screen", "onsite"):
        base = last_contact or applied or today
        start, end = base + timedelta(days=7), base + timedelta(days=21)
        kind, why = "next_step", ("Rule of thumb: after a screen or onsite, the next step "
                                  "usually comes within 1-3 weeks of the last contact.")
    else:
        if not applied:
            return None
        kind = classify(title, company)
        if kind == "mba_cycle":
            start = max(applied + timedelta(days=14), MBA_FIRST_WORD)
            end = MBA_INTERVIEWS_END
            why = ("MBA internship calendar: Haas runs company events Oct 26 - Nov 19 and "
                   "interviews Jan 19 - Feb 18, 2027. First word usually lands in that span.")
        elif kind == "off_cycle":
            start, end = applied + timedelta(days=7), applied + timedelta(days=35)
            why = ("Off-cycle internships hire close to their start date, so they move "
                   "fast: usually 1-5 weeks.")
        elif kind == "structured":
            start, end = applied + timedelta(days=21), applied + timedelta(days=75)
            why = ("Large-company intern programs screen in batches: usually 3-11 weeks, "
                   "often longer for summer roles posted early.")
        else:
            start, end = applied + timedelta(days=7), applied + timedelta(days=42)
            why = ("Startups hire on a rolling basis: usually 1-6 weeks. Past about "
                   "8 weeks, silence is usually the answer.")
    if today < start:
        state = "early"
    elif today <= end:
        state = "window"
    elif kind == "rolling" and today > end + timedelta(days=18):
        state = "likely_no"
    else:
        state = "overdue"
    label = f"{start.strftime('%b %-d')} - {end.strftime('%b %-d')}"
    return {"kind": kind, "label": label, "from": start.isoformat(), "to": end.isoformat(),
            "state": state, "why": why}
