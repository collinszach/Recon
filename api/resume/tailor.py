"""Tailor the master resume to a specific role — Claude returns a match analysis
(score, strengths, gaps, ATS keywords, a tailored summary, and rewritten bullets).
Suggestions only; the human decides what to use. Never fabricates experience."""
import json
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from config import settings
from db import Resume, ResumeExperience, Role

log = logging.getLogger("recon.tailor")

SYSTEM = """\
You are a sharp technical-recruiting partner helping Zach Collins tailor his resume to a
specific role. Use ONLY the experience in his resume — never invent employers, titles, metrics,
or skills he doesn't have. Rephrasing and emphasis are fine; fabrication is not. Be concrete and
specific to this role; prefer his real, quantified accomplishments.
"""

INSTRUCTIONS = """\
Given Zach's resume and a target role, respond with ONLY a JSON object (no prose, no fences):
{
  "match_score": <float 0-10, how well his real background fits this role>,
  "verdict": "<=2 sentences on overall fit",
  "strengths": ["specific resume points that map to this role", ...],
  "gaps": ["what's missing or under-evidenced for this role; be honest", ...],
  "keywords": ["ATS/role keywords worth surfacing if truthful", ...],
  "tailored_summary": "a 2-3 sentence professional summary rewritten for THIS role, truthful",
  "suggested_bullets": ["3-5 resume bullets reworded to emphasize fit for this role, no fabrication", ...]
}
"""


def assemble_resume(db: Session) -> str:
    r = db.scalar(select(Resume).limit(1))
    if not r:
        return ""
    parts = [f"NAME: {r.full_name}", f"HEADLINE: {r.headline}", f"LOCATION: {r.location}",
             f"SUMMARY: {r.summary}", f"SKILLS:\n{r.skills}", f"EDUCATION:\n{r.education}"]
    exps = db.scalars(select(ResumeExperience).order_by(ResumeExperience.sort_order)).all()
    for kind in ("work", "project", "leadership"):
        rows = [e for e in exps if e.kind == kind]
        if rows:
            parts.append(f"\n{kind.upper()}:")
            for e in rows:
                hdr = " | ".join(x for x in (e.company, e.title, e.location,
                                             f"{e.start_date}–{e.end_date}" if e.start_date else None) if x)
                parts.append(hdr)
                for b in (e.bullets or "").split("\n"):
                    if b.strip():
                        parts.append(f"  - {b.strip()}")
    return "\n".join(parts)


def _role_blob(role: Role) -> str:
    co = role.company.name if role.company else "?"
    bits = [f"COMPANY: {co}", f"TITLE: {role.title}", f"LOCATION: {role.location}",
            f"DOMAIN: {role.domain}", f"URL: {role.url}"]
    if role.why_fit:
        bits.append(f"PRIOR FIT NOTE: {role.why_fit}")
    return "\n".join(b for b in bits if b)


def tailor_role(db: Session, role: Role) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Resume tab."}
    if settings.scoring_mode != "live" or not settings.anthropic_api_key:
        return {"error": "Tailoring needs SCORING_MODE=live and an ANTHROPIC_API_KEY."}

    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"{INSTRUCTIONS}\n\n=== RESUME ===\n{resume}\n\n=== TARGET ROLE ===\n{_role_blob(role)}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    # Be forgiving: extract the outermost JSON object if the model added prose.
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("tailor: could not parse JSON for role %s: %r", role.id, text[:300])
        return {"error": "Couldn't parse the tailoring response. Try again."}
    data["_cost_usd"] = round(msg.usage.input_tokens * 3e-6 + msg.usage.output_tokens * 15e-6, 4)
    return data
