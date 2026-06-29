"""Research WHO to reach out to at a target company for a role.

Returns target *personas* (role-types worth contacting) — never invented named
individuals, since we have no way to verify a real person exists. Each target
comes with why-them, where-to-find (a LinkedIn search Zach can run himself),
and a short, truthful opener grounded in his real resume and Berkeley network.
"""
import json
import logging
from urllib.parse import quote_plus
from sqlalchemy.orm import Session
import llm
from config import settings
from db import Role
from resume.tailor import assemble_resume

log = logging.getLogger("recon.networking")

SYSTEM = """\
You plan a networking approach for Zach Collins (technical PM, Berkeley MBA/MEng '28) targeting a
specific role at a specific company. Output the PEOPLE-TYPES he should reach out to — ranked by
expected payoff — to get a referral or an informational conversation.

Hard rules:
- NEVER invent a real named person, their title, or their tenure. Describe TARGET PERSONAS by
  role/function only (e.g. "PM on the team that owns this product", "Berkeley Haas/MEng alum now
  in product here", "the likely hiring manager — a Group PM or Director of Product").
- "opener" must use ONLY real facts from his resume. Warm, specific, human — no "I am passionate",
  "I came across", "reaching out", "leverage", "spearheaded". 1-2 sentences he could actually send.
- Prefer warm paths first: Berkeley alumni, shared past employers, second-degree connections.
- "find_hint" is a concrete instruction for locating this persona (job titles to search, the
  alumni angle to use). Keep it actionable.

Respond with ONLY a JSON object (no prose, no fences):
{
  "summary": "<1-2 sentence read on the best way into this company>",
  "targets": [
    {
      "persona": "<role/function to contact, e.g. 'Senior PM on the data platform team'>",
      "warmth": "warm | medium | cold",
      "why": "<why this person can move the needle for THIS role>",
      "find_hint": "<how to find them: titles to search + alumni/shared-employer angle>",
      "opener": "<1-2 sentence message grounded in his real resume>"
    }
  ]
}
Give 3-5 targets, best path first."""


def who_to_reach(db: Session, role: Role) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Résumé tab first."}
    if settings.scoring_mode != "live" or not llm.configured():
        return {"error": "Networking research needs SCORING_MODE=live and an LLM backend configured."}

    co = role.company.name if role.company else "the company"
    role_blob = f"COMPANY: {co}\nROLE: {role.title}\nLOCATION: {role.location}\nDOMAIN: {role.domain}"
    if role.why_fit:
        role_blob += f"\nWHY IT FITS HIM: {role.why_fit}"

    res = llm.complete(
        system=SYSTEM, max_tokens=1100,
        messages=[{"role": "user",
                   "content": f"=== RESUME ===\n{resume}\n\n=== TARGET ROLE ===\n{role_blob}"}],
    )
    text = res.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("networking: unparseable for role %s", role.id)
        return {"error": "Couldn't research that — try again."}

    # attach a ready-to-run LinkedIn people search per target (no scraping, just a deep link)
    for t in data.get("targets", []):
        terms = " ".join(x for x in [t.get("persona", ""), co] if x)
        t["linkedin_search"] = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(terms)}"
    return {"summary": data.get("summary"), "targets": data.get("targets", [])}
