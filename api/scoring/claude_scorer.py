"""Score roles against Zach's profile via Claude. Stub mode runs free."""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import llm
from config import settings
from db import Role

log = logging.getLogger("recon.scoring")

# Approx Claude pricing, USD per (input, output) token — update if pricing changes.
PRICING = {
    "claude-haiku-4-5": (1.0 / 1_000_000, 5.0 / 1_000_000),
    "claude-sonnet-4-6": (3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-opus-4-8": (5.0 / 1_000_000, 25.0 / 1_000_000),
}

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

He can credibly own and add value across technical / data-platform / AI / cloud / API /
infrastructure / hardware-adjacent work and partners deeply with engineering. He is a TECHNICAL
operator, not a generalist non-technical PM.

SCORING STANCE — judge every role on how well it fits HIS BACKGROUND and trajectory, NOT on its
industry or its exact title:
- INDUSTRY-NEUTRAL: do not weight any sector up or down. Defense, commercial, aerospace, fintech,
  health, robotics, climate, consumer, gov-tech — all equal; score purely on role fit. Still tag
  the closest domain below, but that tag must NOT change the score or tier.
- ROLE-TYPE-BROAD: score ANY role his background suits, on merit — product management AND adjacent
  paths: technical PM / TPM, program / project (when technical), solutions / forward-deployed
  engineering, developer relations, BizOps / Strategy & Ops / Chief of Staff, GM, and eng-adjacent
  IC or lead roles. Do NOT downgrade a role just because it isn't "pure product."
- TECHNOLOGY & INNOVATION ARE A POSITIVE SIGNAL: roles building genuinely interesting, cutting-edge,
  or frontier technology (autonomy, AI/ML, robotics, space, advanced hardware, novel platforms) are
  a PLUS in any sector — he's drawn to hard, innovative tech.
His background spans a federal supply chain (SAP EWM/TM), an MBSE digital-twin on a defense Smart
MRO, and a Collins Aerospace (Raytheon) internship, so defense / aerospace / hardware roles fit him
well — but treat that as fit, not as an industry preference.

CAREER TRAJECTORY: end goal is FOUNDER, CTO, or COO. Rank UP roles with broad scope, ownership /
P&L, 0->1 building, real technical depth, and a clear runway toward GM or the exec suite; rank down
narrow IC tracks with little growth.

LOCATION PREFERENCE: Zach will RELOCATE for the right role, and actively favors these metros:
Charleston SC, New York City, the DC / Northern-Virginia / Maryland area, Southern California
(LA / Orange County / San Diego / Irvine), Greater Boston, and Pennsylvania (Philadelphia /
Pittsburgh) — plus US-remote. When the role blob includes a "TARGET METRO" line, treat the
location as a positive (it's where he wants to be); do NOT downgrade it as "would require a move."
A role in none of those is location-neutral, not a penalty — judge it on merit.

DOMAIN TAG — pick the closest (for filtering only; does NOT weight the score):
  AI&Data | SCM&Twins | Hardware | Venture | Finance | Platform | Defense | Aerospace | other
"""

INTERN_PROFILE = _CANDIDATE + """
CURRENT GOAL: land a SUMMER 2027 INTERNSHIP (the summer between the two program years; a return
offer sets up full-time recruiting). Product/APM is the sweet spot, but any internship his
technical/operator background fits is in scope.

HARD RULES (internship lens):
- Score how good a fit the posting is as a Summer 2027 internship for HIS background.
- TERM: target is Summer 2027. A role explicitly tied to a DIFFERENT summer (e.g. "Summer 2025"
  or "Summer 2026" only, with no 2027 cohort) is off-cycle -> tier "pass", note the term. A role
  with no stated year, or an MBA/grad internship that recruits a year ahead, is fine — most
  Summer 2027 reqs are not posted yet, so an unspecified-year internship at a fitting company is
  a strong WATCH.
- ROLE TYPE IS BROAD: product / APM, but also TPM, technical program/project, strategy/ops,
  solutions, and eng-adjacent internships all score on merit. is_product_pm is INFORMATIONAL
  (true only for genuine product roles) and does NOT cap the tier. Interesting technology is a plus.
- A FULL-TIME role that slipped through is NOT what this lens wants -> tier "pass".
- Weight WLB positively; put the HOURLY or MONTHLY wage/stipend (not annual TC) in tc_estimate if
  stated — do not invent a number, and don't penalize on stipend.

TIERS (internship):
  A = strong Summer-2027-eligible internship with a clear fit to his background and ideally
      interesting technology.
  B = good internship fit with one tradeoff (role-type stretch, WLB, off-fit team, or stage risk).
  C = thin fit to his background, or a weak technical/innovation surface.
  pass = full-time role, off-cycle (non-2027) internship, or clear misfit.
"""

FULLTIME_PROFILE = _CANDIDATE + """
CURRENT GOAL: map the FULL-TIME market — roles Zach would target post-graduation (2028) or convert
into from an internship. Score any full-time role his background fits, not just product roles.

HARD RULES (full-time lens):
- ROLE TYPE IS BROAD: product management AND adjacent paths (technical PM/TPM, technical program/
  project, solutions / forward-deployed, developer relations, BizOps / strategy, GM, eng-adjacent
  IC or lead) all score on merit. is_product_pm is INFORMATIONAL (set true for genuine product
  roles, false otherwise) and does NOT cap the tier.
- COMP IS A SOFT PREFERENCE, NOT A GATE: ~$200K+ TC is the target and higher is better, but do NOT
  cap the tier on comp alone. Put the TC range in tc_estimate if stated; never invent a number. A
  strong-fit role with unknown or below-target comp can still be A or B.
- SENIORITY: Zach is early-career (incoming MBA/MEng, ~few yrs experience). Senior/Staff/Principal/
  Director/VP/Head roles likely out-reach his level — note it as a concern and cap the tier UNLESS
  the role is explicitly new-grad / early-career / APM / rotational.
- Weight WLB positively; brutal-hours cultures are a downgrade. Interesting / frontier technology
  is a plus in any sector.
- An INTERNSHIP is not what this lens wants -> tier "pass".

TIERS (full-time):
  A = strong-fit role for his technical/operator background with real scope and attainable level;
      target-or-above comp and cool technology are pluses, not requirements.
  B = good fit with one tradeoff (level stretch, scope, comp, or stage risk).
  C = thin fit to his background, big seniority mismatch, or weak technical/innovation surface.
  pass = internship, or clear misfit (wrong background entirely).
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
- COMP is a soft preference (~$200K+ target, higher better), not a gate — don't cap the tier on
  comp alone. All sectors are equal (industry-neutral); WLB-weighted; interesting tech is a plus.
- Seniority: he's early-career — Director/VP/Head roles likely stretch; note it and cap the tier
  unless the role is explicitly open to his level.
- is_product_pm should be FALSE for ops/strategy roles (informational tag; doesn't cap the tier).

TIERS (ops/strategy):
  A = strong strategy/ops/GM role with founder-track scope and attainable level.
  B = good fit with one tradeoff (level stretch, narrow scope, comp, WLB).
  C = execution-heavy or narrow ops, or thin fit to his background.
  pass = internship, pure product-PM, excluded technical/field ops, or clear misfit.
"""

INSTRUCTIONS = """\
Score the role below. Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "fit_score": <float 0-10>,
  "tier": "A" | "B" | "C" | "pass",
  "domain": "AI&Data" | "SCM&Twins" | "Hardware" | "Venture" | "Finance" | "Platform" | "Defense" | "Aerospace" | "other",
  "why_fit": "<= 2 sentences, specific to this JD",
  "concerns": "<= 1 sentence or null",
  "curriculum_hook": "which course(s) this role justifies, or null",
  "tc_estimate": "range string or null",
  "is_product_pm": <true|false>
}
"""


def _role_blob(role: Role) -> str:
    co = role.company.name if role.company else "?"
    blob = (f"COMPANY: {co} (tier {role.company.tier if role.company else '?'})\n"
            f"TITLE: {role.title}\nLOCATION: {role.location}\n")
    if role.metro:
        from scan.geo import METROS
        label = dict(METROS).get(role.metro, role.metro)
        blob += f"TARGET METRO: {label} (a metro Zach is targeting)\n"
    blob += f"DEPARTMENT: {role.department}\nURL: {role.url}"
    if role.description:
        # The JD is the strongest fit signal; cap it so bulk scoring stays cheap.
        jd = " ".join(role.description.split())[:2500]
        blob += f"\n\nJOB DESCRIPTION:\n{jd}"
    return blob


def score_roles(db: Session, roles: list[Role]) -> dict:
    if settings.scoring_mode != "live" or not llm.configured():
        return _score_stub(db, roles)
    return _score_live(db, roles)


def _apply(role: Role, data: dict) -> None:
    role.fit_score = float(data.get("fit_score") or 0)
    # No product-only clamp: roles are scored on fit to Zach's background, and
    # adjacent / non-product roles can sit in A/B on merit (rubric, 2026-06-28).
    # is_product_pm is kept as an informational tag only.
    role.score_tier = data.get("tier")
    role.domain = data.get("domain")
    role.why_fit = data.get("why_fit")
    role.concerns = data.get("concerns")
    role.curriculum_hook = data.get("curriculum_hook")
    role.tc_estimate = data.get("tc_estimate")
    role.is_product_pm = data.get("is_product_pm")
    role.scored_at = datetime.now(timezone.utc)


def _score_stub(db: Session, roles: list[Role]) -> dict:
    """Heuristic scorer — lets the whole pipeline run with zero API spend.
    Background-fit-aware (not product-gated): rewards product/technical roles,
    scores adjacent roles on merit, flags off-cycle summers from the title."""
    import re
    from scan.intern_filter import is_internship
    target = str(settings.intern_target_year)
    senior = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|vp|vice\s+president|head)\b", re.I)
    # Title words that signal a role his technical/operator background fits.
    techy = re.compile(r"\b(product|technical|platform|data|ai|ml|software|engineer|engineering|"
                       r"solutions|strategy|operations|ops|program|project|analytics|cloud|"
                       r"infrastructure|developer|hardware|robotics|autonomy)\b", re.I)
    for r in roles:
        t = (r.title or "").lower()
        is_product = "product" in t
        fits = bool(techy.search(t))          # adjacent/technical roles count, not just product
        intern = is_internship(r.title, r.department)
        years = re.findall(r"\b(20\d{2})\b", t)
        off_cycle = bool(years) and target not in years and intern
        concern = None
        if intern:
            if off_cycle:
                score, tier, concern = 2.0, "pass", f"Off-cycle: title names {','.join(years)}, not {target}."
            elif fits:
                score = 7.0 + (1.0 if r.company and r.company.tier == "A" else 0.0)
                tier = "A" if score >= 8 else "B"
            else:
                score, tier = 5.0, "C"
        else:  # full-time lens
            if fits and senior.search(t):
                score, tier, concern = 6.0, "C", "Likely above an early-career seniority level."
            elif fits:
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
            "is_product_pm": is_product,
        })
    db.commit()
    log.info("stub-scored %d roles", len(roles))
    return {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}


def _score_live(db: Session, roles: list[Role]) -> dict:
    from scan.intern_filter import is_internship, is_ops_strategy
    tok_in = tok_out = 0

    for r in roles:
        # Pick the lens that matches the role: internship, ops/strategy, or product.
        if is_internship(r.title, r.department):
            profile = INTERN_PROFILE
        elif is_ops_strategy(r.title, r.department):
            profile = OPS_PROFILE
        else:
            profile = FULLTIME_PROFILE
        res = llm.complete(
            system=profile,
            max_tokens=400,
            model=settings.scoring_model,
            messages=[{"role": "user", "content": INSTRUCTIONS + "\n\nROLE:\n" + _role_blob(r)}],
        )
        tok_in += res.tokens_in
        tok_out += res.tokens_out
        text = res.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            _apply(r, json.loads(text))
        except json.JSONDecodeError:
            log.warning("could not parse score for role %s", r.id)
    db.commit()

    # gs65 (local) is free; only the Claude API bills per token.
    if settings.llm_provider == "anthropic":
        price_in, price_out = PRICING.get(settings.scoring_model, PRICING["claude-haiku-4-5"])
        usd = tok_in * price_in + tok_out * price_out
    else:
        usd = 0.0
    log.info("live-scored %d roles, $%.4f", len(roles), usd)
    return {"tokens_in": tok_in, "tokens_out": tok_out, "usd": round(usd, 4)}
