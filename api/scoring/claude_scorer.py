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

_CANDIDATE = """\
CANDIDATE PROFILE — Zach Collins
- Incoming UC Berkeley concurrent MBA (Haas) + MEng (Mechanical Engineering), class of 2028.
- TECHNICAL PRODUCT MANAGER. PM on enterprise SAP EWM/TM supply-chain systems for large
  institutional clients; 100+ production releases shipped into demanding environments.
- ENGINEERING LEADERSHIP: has led software development teams AND data-engineering teams;
  built and shipped cloud applications end-to-end.
- DEEP TECHNICAL STACK (hands-on, not just certified): AWS (Solutions Architect certified;
  built and ran applications in the cloud), Databricks, data engineering & pipelines, REST APIs,
  SQL, AI/ML integration, vector DBs, time-series (Postgres/TimescaleDB), Docker, FastAPI,
  Next.js. Ships production data systems solo.
- Credentials: AWS Solutions Architect, CompTIA Security+, ME degree (summa cum laude).
- Custom MEng concentration: ML (ME 276DS), digital twins (ME 239), embedded hardware (ME 235),
  new product development (ME 290P).
- Active surfer, trail runner, tennis player, car enthusiast — authentic user of outdoor/athlete tech.

He can credibly OWN technical / data-platform / AI / cloud / API / infrastructure product
areas and partner deeply with engineering. Weight technical-PM, data, AI, cloud, platform, and
developer-facing roles UP; he is not a generalist non-technical PM.

DEFENSE / NATIONAL SECURITY IS IN SCOPE and a genuine strength, not a penalty: his Deloitte work
ran a mission-critical FEDERAL supply chain (SAP EWM/TM), he led an MBSE digital-twin initiative
on a DEFENSE Smart MRO facility, and he interned at Collins Aerospace (Raytheon). Defense-tech
PRODUCT roles (autonomy, defense data platforms, hardware, space) should be ranked on merit and
treated as a priority domain — his cleared-adjacent, federal, and hardware background is an edge.

CAREER TRAJECTORY: end goal is FOUNDER, CTO, or COO. He is OPEN TO OPERATIONS / STRATEGY roles
(BizOps, Strategy & Ops, Chief of Staff, GM, corp dev) as a path to general management and the
founder track — value broad scope, ownership/P&L, 0->1 building, and a clear runway to GM or the
exec suite. He is also OPEN TO THE AVIATION / AEROSPACE sector where applicable (Collins Aerospace
background + ME degree). Rank roles that build toward founder/CTO/COO higher than narrow IC tracks.

PRIORITY DOMAINS (map each role to the closest one):
  AI&Data | SCM&Twins | Hardware | Venture | Finance | Platform | Defense | Aerospace | other
"""

INTERN_PROFILE = _CANDIDATE + """
CURRENT GOAL: land a SUMMER 2027 PRODUCT-MANAGEMENT / APM INTERNSHIP (the internship summer
between the two program years; a return offer sets up full-time recruiting).

HARD RULES (internship lens):
- Score how good a fit the posting is as a Summer 2027 internship.
- TERM: target is Summer 2027. A role explicitly tied to a DIFFERENT summer (e.g. "Summer 2025"
  or "Summer 2026" only, with no 2027 cohort) is off-cycle -> tier "pass", note the term. A role
  with no stated year, or an MBA/grad internship that recruits a year ahead, is fine — most
  Summer 2027 reqs are not posted yet, so an unspecified-year internship at a target company is
  a strong WATCH.
- "PM" must mean PRODUCT management, not program/project management. If program/project, set
  is_product_pm=false and tier no higher than "C".
- COMMERCIAL and DEFENSE/national-security product internships are both in scope and ranked on
  merit — defense is a priority domain given his federal/MBSE/aerospace background, not a penalty.
- A FULL-TIME role that slipped through is NOT what this lens wants -> tier "pass".
- Weight WLB positively; put the HOURLY or MONTHLY wage/stipend (not annual TC) in tc_estimate if
  stated — do not invent a number.

TIERS (internship):
  A = strong Summer-2027-eligible PRODUCT/APM internship at a target-domain company, clear fit.
  B = good internship fit with one tradeoff (domain stretch, WLB, off-priority team, or stage risk).
  C = passion/lifestyle internship, below-priority domain, or program/project internship.
  pass = full-time role, off-cycle (non-2027) internship, or clear misfit.
"""

FULLTIME_PROFILE = _CANDIDATE + """
CURRENT GOAL: map the FULL-TIME PRODUCT-MANAGEMENT career market — roles Zach would target
post-graduation (2028) or convert into from an internship. Score full-time product roles.

HARD RULES (full-time lens):
- "PM" must mean PRODUCT management, not program/project management. If program/project, set
  is_product_pm=false and tier no higher than "C".
- COMMERCIAL and DEFENSE/national-security product roles are both in scope and ranked on merit;
  defense-tech (autonomy, defense data platforms, hardware, space) is a priority domain for him,
  not a downgrade — his federal supply chain, MBSE-on-defense-MRO, and aerospace background fit.
- $200K+ total comp is the floor; $300K+ is the target. Put the TC range in tc_estimate if
  stated; do not invent a number. Clearly below-floor roles are tier C at best unless an
  exceptional lifestyle/passion fit.
- SENIORITY: Zach is early-career (incoming MBA/MEng, ~few yrs PM experience). Senior/Staff/
  Principal/Director/VP/Head-of-Product roles likely out-reach his level — note it as a concern
  and cap the tier, UNLESS the role is explicitly new-grad / early-career / APM / rotational.
- Weight WLB positively; brutal-hours cultures are a downgrade.
- An INTERNSHIP is not what this lens wants -> tier "pass".

TIERS (full-time):
  A = strong commercial PRODUCT role, on-target comp, clear domain match, attainable seniority.
  B = good fit with one tradeoff (comp ceiling, WLB, seniority stretch, or stage risk).
  C = below-floor comp for passion/brand, domain stretch, or program/project role.
  pass = internship, clear seniority mismatch, or misfit.
"""

OPS_PROFILE = _CANDIDATE + """
CURRENT GOAL (ops lens): map full-time OPERATIONS / STRATEGY roles that build toward GM / founder
/ CTO / COO. Score business-operations, strategy, chief-of-staff, corp-dev, and GM roles.

HARD RULES (ops/strategy lens):
- In scope: BizOps, Strategy & Operations, Chief of Staff, Corporate Strategy/Development, RevOps,
  GTM strategy, General Manager. NOT here: pure product PM (own track), internships, or narrow
  technical/field ops (security/network/IT/clinical/warehouse/flight ops).
- His edge: technical PM + engineering, AWS/data, SCM/federal background, MEng/MBA — strong for
  technical ops, data/analytics-driven strategy, supply-chain ops, and platform/GM roles.
- FOUNDER/CTO/COO runway: rank UP roles with broad scope, ownership/P&L, 0->1 building, and a path
  to GM or the exec suite. Rank DOWN execution-only ops with no strategic surface.
- $200K+ floor / $300K+ target; commercial, defense, and aerospace all in scope; WLB-weighted.
- Seniority: he's early-career — Director/VP/Head roles likely stretch; note it and cap the tier
  unless the role is explicitly open to his level.
- is_product_pm should be FALSE for ops/strategy roles (they're not product management).

TIERS (ops/strategy):
  A = strong strategy/ops/GM role with founder-track scope, attainable level, clear domain fit.
  B = good fit with one tradeoff (level stretch, narrow scope, comp ceiling, WLB).
  C = execution-heavy or narrow ops, domain stretch, or below-floor for brand/passion.
  pass = internship, pure product-PM, excluded technical/field ops, or clear misfit.
"""

INSTRUCTIONS = """\
Score the role below. Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "fit_score": <float 0-10>,
  "tier": "A" | "B" | "C" | "pass",
  "domain": "AI&Data" | "SCM&Twins" | "Hardware" | "Venture" | "Finance" | "Platform" | "Defense" | "other",
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
    tier = data.get("tier")
    # Deterministic guardrail: "PM must mean PRODUCT". A non-product internship
    # can't sit in the top tiers no matter how the model felt about the company.
    if data.get("is_product_pm") is False and tier in ("A", "B"):
        tier = "C"
    role.score_tier = tier
    role.domain = data.get("domain")
    role.why_fit = data.get("why_fit")
    role.concerns = data.get("concerns")
    role.curriculum_hook = data.get("curriculum_hook")
    role.tc_estimate = data.get("tc_estimate")
    role.is_product_pm = data.get("is_product_pm")
    role.scored_at = datetime.now(timezone.utc)


def _score_stub(db: Session, roles: list[Role]) -> dict:
    """Heuristic scorer — lets the whole pipeline run with zero API spend.
    Intern-aware: rewards product internships, downgrades program/project ones,
    flags off-cycle summers it can read from the title."""
    import re
    from scan.intern_filter import is_internship
    target = str(settings.intern_target_year)
    senior = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|vp|vice\s+president|head)\b", re.I)
    for r in roles:
        t = (r.title or "").lower()
        is_product = "product" in t
        is_program = ("program" in t or "project" in t) and not is_product
        intern = is_internship(r.title, r.department)
        years = re.findall(r"\b(20\d{2})\b", t)
        off_cycle = bool(years) and target not in years and intern
        concern = None
        if intern:
            if off_cycle:
                score, tier, concern = 2.0, "pass", f"Off-cycle: title names {','.join(years)}, not {target}."
            elif is_program:
                score, tier, concern = 3.5, "C", "Program/project internship, not product."
            elif is_product:
                score = 7.0 + (1.0 if r.company and r.company.tier == "A" else 0.0)
                tier = "A" if score >= 8 else "B"
            else:
                score, tier = 5.0, "C"
        else:  # full-time lens
            if is_program:
                score, tier, concern = 3.5, "C", "Program/project role, not product."
            elif is_product and senior.search(t):
                score, tier, concern = 6.0, "C", "Likely above an early-career seniority level."
            elif is_product:
                score = 7.0 + (1.0 if r.company and r.company.tier == "A" else 0.0)
                tier = "A" if score >= 8 else "B"
            else:
                score, tier = 5.0, "C"
        _apply(r, {
            "fit_score": min(score, 10),
            "tier": tier,
            "domain": "other",
            "why_fit": "Heuristic stub score — enable SCORING_MODE=live for real scoring.",
            "concerns": concern,
            "curriculum_hook": None,
            "tc_estimate": None,
            "is_product_pm": bool(is_product and not is_program),
        })
    db.commit()
    log.info("stub-scored %d roles", len(roles))
    return {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}


def _score_live(db: Session, roles: list[Role]) -> dict:
    from anthropic import Anthropic
    from scan.intern_filter import is_internship, is_ops_strategy
    client = Anthropic(api_key=settings.anthropic_api_key)
    tok_in = tok_out = 0

    for r in roles:
        # Pick the lens that matches the role: internship, ops/strategy, or product.
        if is_internship(r.title, r.department):
            profile = INTERN_PROFILE
        elif is_ops_strategy(r.title, r.department):
            profile = OPS_PROFILE
        else:
            profile = FULLTIME_PROFILE
        msg = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=profile,
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
