"""Backend for the Recon Autofill Chrome extension: a flat profile dict for
structured field-filling (no LLM), and LLM-drafted answers for free-text/essay
questions on job application forms. Same truthful-only guardrail as tailor.py/
cover.py — never invent experience the resume doesn't back up."""
import json
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
import llm
from config import settings
from db import AutofillProfile, Resume
from resume.tailor import assemble_resume

log = logging.getLogger("recon.autofill")

SYSTEM = """\
You are helping Zach Collins answer a job application question. Use ONLY real facts from
his resume — never invent employers, titles, metrics, or skills he doesn't have. Be concise,
specific, and match the format the question implies (a short answer field wants 1-3 sentences,
an essay/textarea question wants a full paragraph or two). Plain, direct voice — no clichés
like "I am passionate" or "I am excited to apply".
"""

INSTRUCTIONS = """\
Given Zach's resume, the target role, and a list of application questions, respond with ONLY
a JSON object (no prose, no fences):
{ "answers": [ { "id": "<question id, echoed back exactly>", "answer": "<drafted answer>" }, ... ] }
"""


def assemble_autofill_profile(db: Session) -> dict:
    """Flat dict of contact/EEO/link fields for client-side structured-field matching."""
    r = db.scalar(select(Resume).limit(1))
    p = db.scalar(select(AutofillProfile).limit(1))
    out: dict = {}
    if r:
        parts = (r.full_name or "").split(" ", 1)
        out.update({
            "full_name": r.full_name,
            "first_name": parts[0] if parts else None,
            "last_name": parts[1] if len(parts) > 1 else None,
            "headline": r.headline,
            "location": r.location,
            "links": r.links,
        })
    if p:
        out.update({
            "phone": p.phone, "email": p.email,
            "address_line1": p.address_line1, "city": p.city, "state": p.state,
            "zip_code": p.zip_code, "country": p.country,
            "linkedin_url": p.linkedin_url, "portfolio_url": p.portfolio_url,
            "github_url": p.github_url,
            "work_authorized": p.work_authorized, "requires_sponsorship": p.requires_sponsorship,
            "willing_to_relocate": p.willing_to_relocate, "pronouns": p.pronouns,
            "veteran_status": p.veteran_status, "disability_status": p.disability_status,
            "gender": p.gender, "race_ethnicity": p.race_ethnicity,
            "desired_salary": p.desired_salary, "earliest_start_date": p.earliest_start_date,
            "notice_period": p.notice_period, "how_heard": p.how_heard,
        })
    return out


def upsert_autofill_profile(db: Session, fields: dict) -> AutofillProfile:
    p = db.scalar(select(AutofillProfile).limit(1))
    if not p:
        p = AutofillProfile(id=1)
        db.add(p)
    for f, v in fields.items():
        if hasattr(p, f):
            setattr(p, f, v)
    db.commit()
    return p


def _role_blob(role_ctx: dict) -> str:
    bits = [f"COMPANY: {role_ctx.get('company', '?')}", f"TITLE: {role_ctx.get('title', '?')}"]
    if role_ctx.get("url"):
        bits.append(f"URL: {role_ctx['url']}")
    if role_ctx.get("description"):
        bits.append(f"DESCRIPTION: {role_ctx['description'][:2000]}")
    return "\n".join(bits)


def answer_questions(db: Session, questions: list[dict], role_ctx: dict) -> dict:
    """questions: [{id, label}]. Returns {"answers": [{id, answer}]} or {"error": ...}."""
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Résumé tab first."}
    if settings.scoring_mode != "live" or not llm.configured():
        return {"error": "Autofill answers need SCORING_MODE=live and an LLM backend configured."}
    if not questions:
        return {"answers": []}

    q_blob = "\n".join(f"- id={q['id']}: {q['label']}" for q in questions)
    res = llm.complete(
        system=SYSTEM, max_tokens=1200,
        messages=[{"role": "user",
                   "content": f"{INSTRUCTIONS}\n\n=== RESUME ===\n{resume}\n\n"
                              f"=== TARGET ROLE ===\n{_role_blob(role_ctx)}\n\n"
                              f"=== QUESTIONS ===\n{q_blob}"}],
    )
    text = res.text.strip().replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        data = json.loads(text)
        return {"answers": data.get("answers", [])}
    except json.JSONDecodeError:
        log.warning("autofill: could not parse JSON: %r", text[:300])
        return {"error": "Couldn't parse the drafted answers. Try again."}
