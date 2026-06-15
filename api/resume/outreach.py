"""Draft tailored cold outreach for a role from Zach's real resume. Suggestion
only — he edits and sends. Never fabricates."""
import json
import logging
from sqlalchemy.orm import Session
from config import settings
from db import Role
from resume.tailor import assemble_resume

log = logging.getLogger("recon.outreach")

SYSTEM = """\
You write cold outreach for Zach Collins (technical PM, Berkeley MBA/MEng '28) to a recruiter,
hiring manager, or PM at a specific company for a specific role.

Rules:
- Use ONLY real facts from his resume — never invent connections, projects, or metrics.
- Warm, concise, specific, human — NOT AI-sounding. No "I am passionate", "I am reaching out",
  "I came across", "spearheaded", "leveraged". Lead with a genuine, concrete reason this role
  fits HIS actual background.
- ~120-160 words. End with a soft, low-pressure ask (a short call / pointing him to the right
  person). Sign off as Zach.

Respond with ONLY a JSON object (no prose, no fences):
{ "subject": "<short email subject, or null>", "draft": "<the message>" }
"""


def draft_outreach(db: Session, role: Role) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Résumé tab first."}
    if settings.scoring_mode != "live" or not settings.anthropic_api_key:
        return {"error": "Outreach drafting needs SCORING_MODE=live and an ANTHROPIC_API_KEY."}

    co = role.company.name if role.company else "the company"
    role_blob = f"COMPANY: {co}\nROLE: {role.title}\nLOCATION: {role.location}\nDOMAIN: {role.domain}"
    if role.why_fit:
        role_blob += f"\nWHY IT FITS HIM: {role.why_fit}"

    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.claude_model, max_tokens=700, system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"=== RESUME ===\n{resume}\n\n=== TARGET ROLE ===\n{role_blob}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("outreach: unparseable for role %s", role.id)
        return {"subject": None, "draft": text or "Couldn't draft that — try again."}
    return {"subject": data.get("subject"), "draft": data.get("draft")}
