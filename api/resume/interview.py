"""AI interview prep for a role — likely questions, talking points grounded in
Zach's real resume, and smart questions for him to ask. Never fabricates."""
import json
import logging
from sqlalchemy.orm import Session
from config import settings
from db import Role
from resume.tailor import assemble_resume

log = logging.getLogger("recon.interviewprep")

SYSTEM = """\
You prep Zach Collins (technical PM, Berkeley MBA/MEng '28) for an interview for a specific role.
Use ONLY his real resume — talking points must map to things he actually did; never invent.

Respond with ONLY a JSON object (no prose, no fences):
{
  "likely_questions": ["5-8 questions he should expect for THIS role/company/level"],
  "talking_points": ["5-7 specific, true stories/strengths from his resume to weave in (STAR-friendly)"],
  "questions_to_ask": ["4-6 sharp questions for HIM to ask the interviewer"],
  "watch_outs": ["1-3 likely gaps/objections and how he should honestly address them"]
}
"""


def interview_prep(db: Session, role: Role) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Résumé tab first."}
    if settings.scoring_mode != "live" or not settings.anthropic_api_key:
        return {"error": "Interview prep needs SCORING_MODE=live and an ANTHROPIC_API_KEY."}

    co = role.company.name if role.company else "the company"
    role_blob = f"COMPANY: {co}\nROLE: {role.title}\nLOCATION: {role.location}\nDOMAIN: {role.domain}"
    if role.why_fit:
        role_blob += f"\nFIT NOTE: {role.why_fit}"
    if role.concerns:
        role_blob += f"\nKNOWN CONCERNS: {role.concerns}"

    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.claude_model, max_tokens=2200, system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"=== RESUME ===\n{resume}\n\n=== ROLE ===\n{role_blob}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("interview_prep: unparseable for role %s", role.id)
        return {"error": "Couldn't generate prep — try again."}
