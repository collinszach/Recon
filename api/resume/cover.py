"""Generate a one-page cover letter for a role from Zach's real resume.
Truthful, in his voice, never fabricated."""
import json
import logging
from sqlalchemy.orm import Session
import llm
from config import settings
from db import Role
from resume.tailor import assemble_resume

log = logging.getLogger("recon.cover")

SYSTEM = """\
Write a cover letter for Zach Collins (technical PM, Berkeley MBA/MEng '28) for a specific role.
Use ONLY real facts from his resume — never invent. Keep it to ONE PAGE (~250-320 words), in his
plain, specific voice (no clichés like "I am passionate", "I am excited to apply", "spearheaded",
"leveraged"). Open with a concrete reason he fits THIS role, give 2 short proof paragraphs from
his real experience, and close with a confident, low-key sign-off.

Respond with ONLY a JSON object (no prose, no fences):
{ "title": "Cover letter — <company> <role>", "content": "<the full cover letter text>" }
"""


def cover_letter(db: Session, role: Role) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Résumé tab first."}
    if settings.scoring_mode != "live" or not llm.configured():
        return {"error": "Cover letters need SCORING_MODE=live and an LLM backend configured."}

    co = role.company.name if role.company else "the company"
    role_blob = f"COMPANY: {co}\nROLE: {role.title}\nDOMAIN: {role.domain}"
    if role.why_fit:
        role_blob += f"\nFIT NOTE: {role.why_fit}"

    res = llm.complete(
        system=SYSTEM, max_tokens=900,
        messages=[{"role": "user", "content": f"=== RESUME ===\n{resume}\n\n=== ROLE ===\n{role_blob}"}],
    )
    text = res.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        data = json.loads(text)
        return {"title": data.get("title", f"Cover letter — {co}"), "content": data.get("content", "")}
    except json.JSONDecodeError:
        return {"title": f"Cover letter — {co}", "content": text}
