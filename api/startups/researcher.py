"""On-demand startup research: a full writeup and a networking-contacts pass.

Mirrors resume/networking.py's pattern (never invent named individuals; ground
openers in Zach's real resume) and resume/tailor.py's use of the quality-tier
Claude model, since these are rare, deliberate calls the user triggers by hand —
not part of the recurring scan/score pipeline. Nothing here runs on a schedule.
"""
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.orm import Session

import llm
from config import settings
from db import Startup, StartupContact
from resume.tailor import assemble_resume

log = logging.getLogger("recon.startups")

DISCOVERY_SYSTEM = """\
You help Zach Collins (incoming Berkeley MBA/MEng, technical PM, founder/CTO/COO trajectory) track
promising startups worth knowing about, learning from, and building relationships with — across
FINTECH, DEFENSE, SUSTAINABILITY/ENERGY, and PRODUCT/TECH/DATA, plus adjacent categories if a
company is notable enough to be worth including ("and beyond" — don't force everything into one of
the four buckets, use "other" when a company is genuinely outside them but still noteworthy).

Hard rules:
- REAL companies only, currently operating. Never invent a company.
- Do not repeat anything in the EXISTING list given to you.
- Prioritize notable, well-funded, or genuinely interesting/innovative companies over obscure ones.
- Prefer some diversity of stage (not only mega-unicorns) and geography.

Respond with ONLY a JSON array, no prose, no markdown fences:
[
  {
    "name": "<company name>",
    "sector": "fintech" | "defense" | "sustainability_energy" | "product_tech_data" | "other",
    "hq_location": "<city, state/country>",
    "stage": "<seed | series A | series B | growth | public | unknown>",
    "one_liner": "<one sentence: what they do>"
  }
]
"""


def discover_candidates(db: Session, n: int = 10) -> list[dict]:
    """Ask Claude to propose `n` real startups not already tracked. Returns raw
    dicts (not yet persisted) — caller decides what to do with them."""
    if not llm.configured():
        return []
    existing = [s.name for s in db.scalars(select(Startup)).all()]
    existing_blob = ", ".join(existing) if existing else "(none yet)"
    # ~150 tokens/company (name+sector+location+stage+one_liner+JSON overhead)
    # plus headroom, capped well under any model's output ceiling.
    max_tokens = min(8000, 200 * n + 400)
    res = llm.complete(
        system=DISCOVERY_SYSTEM, max_tokens=max_tokens, model=settings.claude_model,
        messages=[{"role": "user",
                   "content": f"EXISTING (do not repeat): {existing_blob}\n\nPropose {n} companies."}],
    )
    try:
        data = _parse_json_block(res.text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        log.warning("startup discovery: unparseable response")
        return []


def run_discovery(db: Session, n: int = 10) -> dict:
    """Bulk discovery pass: propose `n` new startups, add each, generate its
    writeup, and auto-persist researched contact personas. This is the only
    function that spends AI cost on startups without an explicit per-company
    ask — called once for the initial seed and, going forward, on a weekly
    schedule from worker/scheduler.py. Every step is defensive (one bad
    company can't kill the batch)."""
    candidates = discover_candidates(db, n)
    added: list[str] = []
    skipped: list[str] = []

    for c in candidates:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        if db.scalar(select(Startup).where(Startup.name == name)):
            skipped.append(name)
            continue
        try:
            s = Startup(name=name, sector=c.get("sector"), hq_location=c.get("hq_location"),
                       stage=c.get("stage"), one_liner=c.get("one_liner"))
            db.add(s)
            db.flush()

            generate_writeup(db, s)

            plan = who_to_reach(db, s)
            for t in (plan.get("targets") or [])[:3]:
                db.add(StartupContact(startup_id=s.id, name=t.get("persona"), role=t.get("persona"),
                                      warmth=t.get("warmth"), notes=t.get("why")))
            db.commit()
            added.append(name)
        except Exception as e:  # one bad company must not kill the batch
            db.rollback()
            log.warning("discovery: failed to add %r: %s: %s", name, type(e).__name__, e)

    log.info("startup discovery: +%d added, %d skipped (already tracked)", len(added), len(skipped))
    return {"added": added, "skipped": skipped}

WRITEUP_SYSTEM = """\
You are researching a startup for Zach Collins — an incoming UC Berkeley MBA/MEng ('28),
technical product manager (enterprise supply-chain systems, AWS-certified, hands-on with cloud/
data engineering), whose end goal is founder, CTO, or COO. He tracks startups across fintech,
defense, sustainability/energy, and product/tech/data to learn the landscape and build relationships
early — this is NOT a job search, it's market and network research.

Write an in-depth, honest brief on the company using your knowledge. Be explicit and prominent
about uncertainty: you have no live data feed (no Crunchbase/PitchBook access), so funding figures,
headcount, and leadership names are your best knowledge and may be stale or wrong — flag anything
you're not confident about rather than stating it as fact.

Respond with ONLY a JSON object (no prose, no fences):
{
  "one_liner": "<one sentence: what they do>",
  "sector_read": "<how this company fits fintech/defense/sustainability-energy/product-tech-data, and why it's interesting>",
  "product_and_market": "<2-4 sentences: product, customers, competitive landscape>",
  "funding_and_stage": "<what you know about funding rounds/investors/stage — caveat confidence>",
  "leadership": "<known founders/execs if you have reasonable confidence — otherwise say so plainly, do not guess>",
  "why_it_matters_to_zach": "<2-3 sentences: why THIS company is worth his attention given his trajectory>",
  "open_questions": ["<things worth verifying directly with the company, not inventable from training data>"]
}
"""

CONTACTS_SYSTEM = """\
You plan a networking approach for Zach Collins (technical PM, Berkeley MBA/MEng '28, founder/CTO/
COO trajectory) toward a specific startup he's tracking for research and relationship-building —
not applying to a specific open role.

Hard rules:
- NEVER invent a real named person, their title, or their tenure. Describe TARGET PERSONAS by
  role/function only (e.g. "a founder or early PM", "Berkeley Haas/MEng alum on the team").
- "opener" must use ONLY real facts from his resume. Warm, specific, human — 1-2 sentences he
  could actually send. No "I am passionate", "reaching out", "leverage", "spearheaded".
- Prefer warm paths first: Berkeley alumni, shared past employers, second-degree connections.
- "find_hint" is a concrete instruction for locating this persona (titles to search, the
  alumni/shared-employer angle to use).

Respond with ONLY a JSON object (no prose, no fences):
{
  "summary": "<1-2 sentence read on the best way into this company>",
  "targets": [
    {
      "persona": "<role/function to contact>",
      "warmth": "warm | medium | cold",
      "why": "<why this person is worth reaching for research/relationship purposes>",
      "find_hint": "<how to find them>",
      "opener": "<1-2 sentence message grounded in his real resume>"
    }
  ]
}
Give 3-5 targets, best path first."""


def _parse_json_block(text: str):
    """Parse a JSON object OR array out of a model response, tolerating stray
    prose/fences around it. Tries a direct parse first (the common case when
    the model followed instructions exactly); only falls back to bracket-
    slicing — tried as an array, then as an object — if that fails, so an
    array response never gets corrupted by object-shaped trimming."""
    text = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in ("[]", "{}"):
        a, b = text.find(open_c), text.rfind(close_c)
        if a != -1 and b != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(text)  # no candidate worked — raise the original-shaped error


def generate_writeup(db: Session, startup: Startup) -> dict:
    """Full in-depth research brief. Cached on the Startup row; only regenerated
    when this is called explicitly (e.g. a fresh POST from the UI)."""
    if not llm.configured():
        return {"error": "Writeup needs an LLM backend configured."}

    blob = f"COMPANY: {startup.name}\n"
    if startup.sector:
        blob += f"TRACKED SECTOR: {startup.sector}\n"
    if startup.hq_location:
        blob += f"HQ: {startup.hq_location}\n"
    if startup.website:
        blob += f"WEBSITE: {startup.website}\n"
    if startup.notes:
        blob += f"ZACH'S NOTES: {startup.notes}\n"

    res = llm.complete(
        system=WRITEUP_SYSTEM, max_tokens=1400, model=settings.claude_model,
        messages=[{"role": "user", "content": blob}],
    )
    try:
        data = _parse_json_block(res.text)
    except json.JSONDecodeError:
        log.warning("startup writeup: unparseable for %s", startup.name)
        return {"error": "Couldn't generate a writeup — try again."}

    markdown = (
        f"## {startup.name}\n\n"
        f"**What they do:** {data.get('one_liner', '')}\n\n"
        f"**Sector fit:** {data.get('sector_read', '')}\n\n"
        f"**Product & market:** {data.get('product_and_market', '')}\n\n"
        f"**Funding & stage:** {data.get('funding_and_stage', '')}\n\n"
        f"**Leadership:** {data.get('leadership', '')}\n\n"
        f"**Why it matters to Zach:** {data.get('why_it_matters_to_zach', '')}\n\n"
        + ("**Worth verifying directly:**\n" + "\n".join(
            f"- {q}" for q in data.get("open_questions", [])) if data.get("open_questions") else "")
    )

    startup.writeup_markdown = markdown
    startup.writeup_generated_at = datetime.now(timezone.utc)
    startup.writeup_model = settings.claude_model
    if not startup.one_liner and data.get("one_liner"):
        startup.one_liner = data["one_liner"]
    if not startup.funding_summary and data.get("funding_and_stage"):
        startup.funding_summary = data["funding_and_stage"]
    db.commit()

    return {"markdown": markdown, "generated_at": startup.writeup_generated_at.isoformat(),
            "raw": data}


def who_to_reach(db: Session, startup: Startup) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"error": "No resume yet — add one in the Résumé tab first."}
    if not llm.configured():
        return {"error": "Networking research needs an LLM backend configured."}

    co_blob = f"COMPANY: {startup.name}"
    if startup.sector:
        co_blob += f"\nSECTOR: {startup.sector}"
    if startup.one_liner:
        co_blob += f"\nWHAT THEY DO: {startup.one_liner}"

    res = llm.complete(
        # 3-5 targets x (persona/why/find_hint/opener) runs verbose — 1100 was
        # observed truncating mid-JSON on every real call (tokens_out==max_tokens).
        system=CONTACTS_SYSTEM, max_tokens=2000,
        messages=[{"role": "user",
                   "content": f"=== RESUME ===\n{resume}\n\n=== TARGET STARTUP ===\n{co_blob}"}],
    )
    try:
        data = _parse_json_block(res.text)
    except json.JSONDecodeError:
        log.warning("startup contacts: unparseable for %s", startup.name)
        return {"error": "Couldn't research that — try again."}

    for t in data.get("targets", []):
        terms = " ".join(x for x in [t.get("persona", ""), startup.name] if x)
        t["linkedin_search"] = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(terms)}"
    return {"summary": data.get("summary"), "targets": data.get("targets", [])}
