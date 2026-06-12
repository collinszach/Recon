"""Score roles against Zach's profile via Claude. Stub mode runs free."""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from config import settings
from db import Role

log = logging.getLogger("recon.scoring")

# Sonnet pricing (approx, USD per token) — update if pricing changes.
PRICE_IN = 3.0 / 1_000_000
PRICE_OUT = 15.0 / 1_000_000

PROFILE = """\
CANDIDATE PROFILE — Zach Collins
- Incoming UC Berkeley concurrent MBA (Haas) + MEng (Mechanical Engineering), class of 2028.
- Background: product manager on enterprise SAP EWM/TM supply-chain systems for large
  institutional clients; 100+ production releases shipped into demanding environments.
- Builder: ships production data systems solo (time-series pipelines, vector DBs, AI routing,
  Postgres/TimescaleDB, Docker, FastAPI, Next.js).
- Credentials: AWS Solutions Architect, CompTIA Security+, ME degree (summa cum laude).
- Custom MEng concentration: ML (ME 276DS), digital twins (ME 239), embedded hardware (ME 235),
  new product development (ME 290P).
- Active surfer, trail runner, tennis player, car enthusiast — authentic user of outdoor/athlete tech.

PRIORITY DOMAINS (map each role to the closest one):
  AI&Data | SCM&Twins | Hardware | Venture | Finance | Platform | other

HARD RULES:
- Target COMMERCIAL product roles. Selling to government is acceptable; serving government
  EXCLUSIVELY is a downgrade. Pure defense/government roles -> lower the score and note it.
- "PM" must mean PRODUCT management, not program/project management. If the role is program/
  project management, set is_product_pm=false and tier no higher than "review".
- $200K+ total comp is the floor; $300K+ is the target. Below-floor roles are tier C at best
  unless an exceptional lifestyle/passion fit.
- Weight work-life balance positively; brutal-hours cultures are a downgrade.

TIERS:
  A = strong commercial fit, on-target comp, clear domain match.
  B = good fit with one tradeoff (comp ceiling, WLB, or risk).
  C = lifestyle/passion bet or below-floor comp accepted for culture/brand.
  pass = program mgmt, exclusively-government, declining business, or clear misfit.
"""

INSTRUCTIONS = """\
Score the role below. Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "fit_score": <float 0-10>,
  "tier": "A" | "B" | "C" | "pass",
  "domain": "AI&Data" | "SCM&Twins" | "Hardware" | "Venture" | "Finance" | "Platform" | "other",
  "why_fit": "<= 2 sentences, specific to this JD",
  "concerns": "<= 1 sentence or null",
  "curriculum_hook": "which course(s) this role justifies, or null",
  "tc_estimate": "range string or null",
  "is_product_pm": <true|false>
}
"""


def _role_blob(role: Role) -> str:
    co = role.company.name if role.company else "?"
    return (f"COMPANY: {co} (tier {role.company.tier if role.company else '?'})\n"
            f"TITLE: {role.title}\nLOCATION: {role.location}\n"
            f"DEPARTMENT: {role.department}\nURL: {role.url}")


def score_roles(db: Session, roles: list[Role]) -> dict:
    if settings.scoring_mode != "live" or not settings.anthropic_api_key:
        return _score_stub(db, roles)
    return _score_live(db, roles)


def _apply(role: Role, data: dict) -> None:
    role.fit_score = float(data.get("fit_score") or 0)
    role.score_tier = data.get("tier")
    role.domain = data.get("domain")
    role.why_fit = data.get("why_fit")
    role.concerns = data.get("concerns")
    role.curriculum_hook = data.get("curriculum_hook")
    role.tc_estimate = data.get("tc_estimate")
    role.is_product_pm = data.get("is_product_pm")
    role.scored_at = datetime.now(timezone.utc)


def _score_stub(db: Session, roles: list[Role]) -> dict:
    """Heuristic scorer — lets the whole pipeline run with zero API spend."""
    for r in roles:
        t = (r.title or "").lower()
        is_pm = "product" in t and "manager" in t or "product manager" in t
        is_program = ("program manager" in t or "project manager" in t) and "product" not in t
        score = 7.0 if is_pm else (3.0 if is_program else 5.0)
        if r.company and r.company.tier == "A":
            score += 1.0
        _apply(r, {
            "fit_score": min(score, 10),
            "tier": "A" if score >= 8 else "B" if score >= 6 else "pass" if is_program else "C",
            "domain": "other",
            "why_fit": "Heuristic stub score — enable SCORING_MODE=live for real scoring.",
            "concerns": "Program/project role, not product." if is_program else None,
            "curriculum_hook": None,
            "tc_estimate": None,
            "is_product_pm": bool(is_pm and not is_program),
        })
    db.commit()
    log.info("stub-scored %d roles", len(roles))
    return {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}


def _score_live(db: Session, roles: list[Role]) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    tok_in = tok_out = 0

    for r in roles:
        msg = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=PROFILE,
            messages=[{"role": "user", "content": INSTRUCTIONS + "\n\nROLE:\n" + _role_blob(r)}],
        )
        tok_in += msg.usage.input_tokens
        tok_out += msg.usage.output_tokens
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            _apply(r, json.loads(text))
        except json.JSONDecodeError:
            log.warning("could not parse score for role %s", r.id)
    db.commit()

    usd = tok_in * PRICE_IN + tok_out * PRICE_OUT
    log.info("live-scored %d roles, $%.4f", len(roles), usd)
    return {"tokens_in": tok_in, "tokens_out": tok_out, "usd": round(usd, 4)}
