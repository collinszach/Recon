"""Turning an email into a pipeline change.

Shared by the API (accept one / accept all) and the mail poller, which files
routine confirmations and rejections on its own. Lived in main.py until the
poller needed it: the worker can't import the web app.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Application, ApplicationEvent, Company, MailMessage


# "Thank you for applying to Lunar Energy" — the shared ATS domains
# (us.greenhouse-mail.io) carry no company at all, so the subject is the only
# place the employer's name appears.
_SUBJECT_COMPANY_RES = [
    # "to"/"at" only, never "for": "submitted application FOR Zachary Collins"
    # names the candidate, and that is exactly what it extracted on the first
    # run — an application filed under Zach's own name.
    re.compile(r"(?:applying|application)\s+(?:to|at)\s+(.+?)[!.?]*$", re.I),
    re.compile(r"^(.+?)\s*[-–]\s*application\s+update", re.I),
    re.compile(r"thank you for your (?:interest in|application to)\s+(.+?)[!.?]*$", re.I),
    re.compile(r"^update from\s+(.+?)[!.?]*$", re.I),             # "Update from Muon Space"
    re.compile(r"\bapplying\s+at\s+(.+?)[!.?]*$", re.I),
]


def _company_from_subject(subject: str | None) -> str | None:
    if not subject:
        return None
    text = re.sub(r"\s+", " ", subject).strip()
    for pat in _SUBJECT_COMPANY_RES:
        m = pat.search(text)
        if m:
            name = re.sub(r"^at\s+", "", m.group(1).strip(" !.,-–—"), flags=re.I)
            # Trim trailing role/req noise: "Acme for the PM Intern role".
            name = re.split(r"\s+\b(for|regarding|re|position|role|req)\b", name, flags=re.I)[0]
            if 2 < len(name) <= 80:
                return name
    return None


def _canonical_company(name: str | None, db: Session) -> str | None:
    """A known spelling of the employer, if Recon has one.

    Workday tenants name the employer in lowercase run-together form
    ("capitalone@myworkday.com" -> "Capitalone"); Recon already knows it as
    "Capital One", and a second spelling is a second, unmatched company.
    """
    if not name:
        return name
    name = re.sub(r"^at\s+", "", name.strip(), flags=re.I)
    squash = re.sub(r"[^a-z0-9]", "", name.lower())
    for known in db.scalars(select(Company.name)).all() + \
            db.scalars(select(Application.company_name)).all():
        if known and re.sub(r"[^a-z0-9]", "", known.lower()) == squash:
            return known
    return name


def _company_from_sender(from_addr: str | None) -> str | None:
    """Company name out of a From header.

    "NVIDIA HR <nvidia@myworkday.com>" -> NVIDIA. Falls back to the sending
    domain when there's no display name, skipping the ATS domains, which name
    the vendor rather than the employer.
    """
    if not from_addr:
        return None
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', from_addr)
    if m:
        # "MasterCard People Services" is Mastercard; "Visa People Team" is Visa.
        # "CapitalOneHRWorkday" -> "Capital One HR Workday"; "do-not-reply adobe" -> "adobe".
        # Split only when that exposes HR/ATS noise — "MasterCard" stays whole.
        disp = m.group(1)
        split = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", disp)
        if re.search(r"\b(HR|Workday|Recruiting|Talent|Careers)\b", split):
            disp = split
        disp = re.sub(r"\b(do[- ]?not[- ]?reply|no[- ]?reply)\b", "", disp, flags=re.I)
        if disp.strip() == disp.strip().lower():
            disp = disp.title()                           # "adobe" -> "Adobe"
        name = re.sub(r"\b(hr|recruiting|recruitment|talent|careers?|team|hiring|"
                      r"people\s+services|people|services|notifications?|"
                      r"workday|icims|greenhouse|lever|ashby)\b", "",
                      disp, flags=re.I)
        name = re.sub(r"@\s*\w*\s*$", "", name)          # "Joby Aviation @ icims"
        name = re.sub(r"\s+", " ", name).strip(" -|,@")
        # A human sender's name is not the company. "Zoe Downey
        # <zoe.downey@skydio.com>" is Skydio — the domain knows, the display
        # name doesn't.
        host_all = (re.search(r"@([\w.-]+)", from_addr) or [None, ""])[1].lower()
        from mail.gmail_client import ATS_SENDERS
        from_ats_domain = any(a in host_all for a in ATS_SENDERS)
        # Only second-guess the display name for non-ATS senders: ATS mail
        # always shows the employer there, and the heuristic below reads
        # two-word company names ("Joby Aviation") as people.
        looks_personal = (not from_ats_domain
                          and bool(re.fullmatch(r"[A-Z][a-z’\']+ [A-Z][a-z’\'-]+", name)))
        if len(name) > 2 and not looks_personal:
            return name[:80]
    # Workday and iCIMS put the tenant in the local part: nvidia@myworkday.com,
    # qualcomm@myworkday.com, amd+autoreply@talent.icims.com.
    local = re.match(r"\s*([\w.+-]+)@", from_addr.split("<")[-1])
    if local:
        tenant = re.split(r"[+.]", local.group(1))[0]
        if tenant.lower() not in {"no-reply", "noreply", "donotreply", "mail",
                                  "info", "careers", "jobs", "hr", "notifications"} \
                and len(tenant) > 2:
            host = (re.search(r"@([\w.-]+)", from_addr) or [None, ""])[1].lower()
            from mail.gmail_client import ATS_SENDERS
            if any(a in host for a in ATS_SENDERS):
                return tenant.replace("-", " ").title()[:80]
    dom = re.search(r"@([\w.-]+)", from_addr)
    if dom:
        host = dom.group(1).lower()
        from mail.gmail_client import ATS_SENDERS
        if any(a in host for a in ATS_SENDERS):
            return None      # names the ATS vendor, not the employer
        # Strip the routing labels employers put in front of the real name:
        # "mail.amazon.jobs" is Amazon, "us.company.com" is Company. Without
        # this the first label wins and applications get created as "Mail"
        # and "Us".
        generic = {"mail", "email", "e", "careers", "career", "jobs", "job",
                   "noreply", "no-reply", "notifications", "notification",
                   "recruiting", "talent", "hire", "hiring", "apply", "info",
                   "hello", "news", "us", "eu", "uk", "my", "www", "smtp"}
        labels = [l for l in host.split(".") if l not in generic]
        # Drop the TLD tail (com/io/co.uk/jobs...). Matched against a known set
        # rather than by length: "e.amd.com" is AMD, and a length rule eats it.
        tlds = {"com", "io", "co", "uk", "net", "org", "ai", "dev", "app", "us",
                "ca", "de", "fr", "inc", "jobs", "careers", "info", "xyz", "tech",
                "aero", "cloud", "digital", "health", "life", "works", "team",
                "me", "tv", "so", "gg", "sh", "fm", "space"}
        while len(labels) > 1 and labels[-1] in tlds:
            labels.pop()
        if labels and labels[-1] in tlds:
            labels.pop()          # single label that is itself a TLD: nothing usable
        if not labels:
            return None
        if labels:
            # "marriotthiring.com" is Marriott: careers sites often glue a
            # hiring word onto the brand.
            name = re.sub(r"(?<=[a-z]{3})(hiring|careers|jobs|recruiting|talent)$", "", labels[-1])
            return name.replace("-", " ").title()[:80]
    return None



def _accept_proposal(m: MailMessage, stage: str | None, db: Session,
                     actor: str = "you") -> dict:
    """The accept itself, without committing — shared by one and all."""
    target = stage or m.proposed_stage
    m.status = "accepted"
    moved = None
    created = None
    # A proposal with no application behind it is one Recon never knew about.
    # Accepting it creates the application from the mail itself — company from
    # the sender's display name, role from the subject where it can be read.
    if not m.application_id:
        # Sender first (it names the employer on most ATS mail), subject as the
        # fallback for shared domains like us.greenhouse-mail.io that name
        # nobody.
        company = _canonical_company(_company_from_sender(m.from_addr)
                                     or _company_from_subject(m.subject), db) or "(unknown)"
        # Accepting the same confirmation twice, or two confirmations for one
        # role, must not make two applications — Atlassian ended up with three.
        from mail.classify import placeholder_title, same_role
        at_company = [a for a in db.scalars(select(Application)).all()
                      if (a.company_name or "").lower() == company.lower()]
        twin = next((a for a in at_company
                     if m.role_title and same_role(a.role_title, m.role_title)), None)
        # The company's only untitled, not-yet-screened application is this
        # one (Mercedes: titled with its confirmation's subject line).
        untitled = [a for a in at_company if placeholder_title(a.role_title)
                    and (a.stage or "applied") in ("watching", "drafting", "applied")]
        if not twin and m.role_title and len(untitled) == 1:
            twin = untitled[0]
        if twin:
            # Attach, then fall through so the proposed stage still applies —
            # attaching a rejection without closing the application is the
            # bug this replaced.
            m.application_id = twin.id
    if not m.application_id:
        app_row = Application(company_name=company,
                              # The role the mail names; the subject only as a
                              # last resort, and then it says it's a subject.
                              role_title=(m.role_title or (m.subject or "")[:200] or None),
                              stage=target or "applied",
                              applied_at=m.received_at or datetime.now(timezone.utc),
                              notes=f"Created from email: {(m.subject or '')[:160]}")
        db.add(app_row)
        db.flush()
        db.add(ApplicationEvent(application_id=app_row.id, from_stage=None,
                                to_stage=app_row.stage, actor=actor, mail_id=m.id,
                                note=f"Created from email from {m.from_addr}"))
        m.application_id = app_row.id
        created = {"id": app_row.id, "company": company}
        return {"status": "ok", "id": m.id, "created_application": created,
                "moved_to": app_row.stage}
    if m.application_id and m.role_title:
        # An application created from an older confirmation is titled with its
        # subject line; this mail knows the real role.
        from mail.classify import placeholder_title
        app_row = db.get(Application, m.application_id)
        if app_row and placeholder_title(app_row.role_title):
            app_row.role_title = m.role_title
    if target and m.application_id:
        app_row = db.get(Application, m.application_id)
        # A confirmation only ever moves a saved application to applied. On
        # 2026-10-20 a same-day Adobe confirmation, accepted after its
        # rejection, reopened the closed application.
        if app_row and m.kind == "ack" and (app_row.stage or "") not in ("watching", "drafting"):
            target = None
        if target and app_row and app_row.stage != target:
            db.add(ApplicationEvent(
                application_id=app_row.id, from_stage=app_row.stage, to_stage=target,
                actor=actor, mail_id=m.id,
                note=f"From email: {(m.subject or '')[:120]} — {m.evidence or ''}"[:500]))
            app_row.stage = target
            if target == "applied" and not app_row.applied_at:
                app_row.applied_at = datetime.now(timezone.utc)
            moved = target
    return {"status": "ok", "id": m.id, "moved_to": moved, "created_application": created}
