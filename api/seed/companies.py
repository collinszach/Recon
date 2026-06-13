"""Seed the target-company list.

Every ats_token below was verified on 2026-06-12 by hitting the live public
ATS endpoint and confirming a non-empty job board (see api/seed/_verify notes
in git history). Companies whose careers site runs a proprietary / login-walled
ATS with no public JSON board are left ats_name='manual' with a note — they are
tracked for context and manual add, not auto-scanned.

Token formats by ATS:
  greenhouse : board slug                      -> boards-api.greenhouse.io/.../{slug}
  ashby      : org slug                        -> api.ashbyhq.com/posting-api/job-board/{slug}
  lever      : org slug                        -> api.lever.co/v0/postings/{slug}
  workday    : "{tenant}:{dc}:{site}"          -> {tenant}.{dc}.myworkdayjobs.com/...

Tiering follows the dashboard rubric: commercial-first, $200K+ TC floor,
product-not-program, WLB-weighted.
  A = strong commercial fit, on-target comp, clear domain match — apply first.
  B = strong swing with one tradeoff (comp ceiling, WLB, or stage risk).
  C = lifestyle / passion / early-stage / below-floor bet.
The `domain` tag in notes is advisory; Claude re-derives domain per role at scan time.
"""
from sqlalchemy import select
from db import SessionLocal, Company

# (name, tier, ats_name, ats_token, careers_url, notes)
SEED = [
    # ════════════════════════════════════════════════════════════════════
    # DASHBOARD TARGETS — the original master-plan board
    # ════════════════════════════════════════════════════════════════════
    # ── Tier A ───────────────────────────────────────────────
    ("Samsara",            "A", "greenhouse", "samsara",        "https://www.samsara.com/company/careers", "SCM&Twins/Hardware · fleet IoT · the anchor target"),
    ("Databricks",         "A", "greenhouse", "databricks",     "https://www.databricks.com/company/careers", "AI&Data · Berkeley-founded, strongest Haas pipeline"),
    ("Rivian",             "A", "manual",     None,             "https://careers.rivian.com",
        "Hardware/EV · Rivian uses iCIMS (no public Greenhouse/Lever/Ashby/Workday board); manual add."),
    ("NVIDIA",             "A", "workday",    "nvidia:wd5:NVIDIAExternalCareerSite", "https://www.nvidia.com/en-us/about-nvidia/careers/", "AI&Data · ~2000 reqs; Workday caps at 250/scan"),
    ("Microsoft",          "A", "manual",     None,             "https://careers.microsoft.com",
        "Cloud/SCM · proprietary career site, not public Workday/Greenhouse; manual add (Aspire MBA PM track)."),
    ("Apple",              "A", "manual",     None,             "https://jobs.apple.com",
        "Hardware · proprietary in-house ATS, no public JSON board; manual add (EPM roles want ME degrees)."),
    # ── Tier B ───────────────────────────────────────────────
    ("Mercury",            "B", "greenhouse", "mercury",        "https://mercury.com/jobs", "Finance · CORRECTED 2026-06-12: was empty on Ashby, live on Greenhouse"),
    ("Celonis",            "B", "greenhouse", "celonis",        "https://www.celonis.com/careers/", "SCM&Twins · process mining over SAP data — your EWM/TM background is their GTM profile"),
    ("Procore",            "B", "workday",    "procore:wd12:Procore_External_Careers", "https://careers.procore.com", "Platform/SCM · construction tech"),
    ("Waymo",              "B", "greenhouse", "waymo",          "https://waymo.com/careers/", "Hardware/Mobility · AV"),
    ("Google Cloud",       "B", "manual",     None,             "https://careers.google.com",
        "Cloud/AI · proprietary in-house ATS, no public board; manual add."),
    ("Meta Reality Labs",  "B", "manual",     None,             "https://www.metacareers.com",
        "Hardware/AR · proprietary in-house ATS, no public board; manual add."),
    # ── Tier C ───────────────────────────────────────────────
    ("onX Maps",           "C", "greenhouse", "onxmaps",        "https://www.onxmaps.com/careers", "Outdoor · you're the user (trail/offroad mapping)"),
    ("Oura",               "C", "greenhouse", "oura",           "https://ouraring.com/careers", "Wearables/Athlete · you're the user"),
    ("Strava",             "C", "ashby",      "strava",         "https://www.strava.com/careers", "Athlete · you're the user (runner/cyclist)"),
    ("Sonos",              "C", "workday",    "sonos:wd1:Sonos", "https://www.sonos.com/careers", "Hardware/Audio"),
    ("Boston Dynamics",    "C", "workday",    "bostondynamics:wd1:Boston_Dynamics", "https://bostondynamics.com/careers/", "Hardware/Robotics"),
    ("WHOOP",              "C", "lever",      "whoop",          "https://www.whoop.com/careers/", "Wearables/Athlete · you're the user"),

    # ════════════════════════════════════════════════════════════════════
    # EXPANDED TARGETS — fitting companies surfaced 2026-06-12, all boards
    # verified live. Grouped by the priority domain they map to.
    # ════════════════════════════════════════════════════════════════════

    # ── SCM & Digital Twins / Fleet (your core background) ────────────────
    ("Motive",             "A", "greenhouse", "gomotive",       "https://gomotive.com/company/careers/", "SCM&Twins/Hardware · DIRECT Samsara competitor (fleet IoT) — your sharpest new fit"),
    ("Flexport",           "A", "greenhouse", "flexport",       "https://www.flexport.com/careers/", "SCM&Twins · freight + shipment digital twins; dashboard-named SCM target"),
    ("project44",          "B", "greenhouse", "project44",      "https://www.project44.com/careers", "SCM&Twins · supply-chain visibility platform"),
    ("FourKites",          "B", "greenhouse", "fourkites",      "https://www.fourkites.com/careers/", "SCM&Twins · real-time supply-chain visibility"),
    ("Anaplan",            "C", "greenhouse", "anaplan",        "https://www.anaplan.com/company/careers/", "SCM&Twins · connected planning"),

    # ── AI & Data ─────────────────────────────────────────────────────────
    ("Scale AI",           "B", "greenhouse", "scaleai",        "https://scale.com/careers", "AI&Data · data infra for ML; dashboard-named"),
    ("OpenAI",             "B", "ashby",      "openai",         "https://openai.com/careers/", "AI&Data · frontier lab; tradeoff: brutal WLB"),
    ("Anthropic",          "B", "greenhouse", "anthropic",      "https://www.anthropic.com/careers", "AI&Data · frontier lab; tradeoff: WLB/intensity"),
    ("dbt Labs",           "B", "greenhouse", "dbtlabsinc",     "https://www.getdbt.com/careers/", "AI&Data · analytics-engineering tooling, data-stack adjacency"),
    ("Glean",              "B", "greenhouse", "gleanwork",      "https://www.glean.com/careers", "AI&Data · enterprise AI search"),
    ("Fivetran",           "B", "greenhouse", "fivetran",       "https://www.fivetran.com/careers", "AI&Data · data integration/ELT"),
    ("Sigma Computing",    "C", "greenhouse", "sigmacomputing", "https://www.sigmacomputing.com/careers", "AI&Data · cloud BI"),
    ("Perplexity",         "C", "ashby",      "perplexity",     "https://www.perplexity.ai/hub/careers", "AI&Data · AI search; early-stage risk"),
    ("Cohere",             "C", "ashby",      "cohere",         "https://cohere.com/careers", "AI&Data · enterprise LLMs"),
    ("Physical Intelligence","C","ashby",     "physicalintelligence", "https://www.physicalintelligence.company/", "AI&Data/Hardware · robot foundation models; very early"),

    # ── Hardware / Robotics / Mobility ───────────────────────────────────
    ("Figure",             "B", "greenhouse", "figureai",       "https://www.figure.ai/careers", "Hardware/Robotics · humanoids; dashboard-named"),
    ("Zipline",            "B", "greenhouse", "flyzipline",     "https://www.flyzipline.com/careers", "Hardware/Logistics · autonomous drone delivery; dashboard-named"),
    ("Skydio",             "B", "ashby",      "skydio",         "https://www.skydio.com/careers", "Hardware · autonomous drones"),
    ("Verkada",            "B", "greenhouse", "verkada",        "https://www.verkada.com/careers/", "Hardware/IoT · physical security; commercial product PM heavy"),
    ("Zoox",               "B", "lever",      "zoox",           "https://zoox.com/careers", "Hardware/Mobility · AV (Amazon)"),
    ("Aurora",             "B", "greenhouse", "aurorainnovation","https://aurora.tech/careers", "Hardware/Mobility · autonomous trucking — SCM adjacency"),
    ("Nuro",               "C", "greenhouse", "nuro",           "https://www.nuro.ai/careers", "Hardware/Mobility · autonomous delivery"),
    ("Lucid Motors",       "C", "greenhouse", "lucidmotors",    "https://www.lucidmotors.com/careers", "Hardware/EV · secondary EV pick behind Rivian"),
    ("Carbon Robotics",    "C", "greenhouse", "carbonrobotics", "https://carbonrobotics.com/careers", "Hardware/Robotics · ag automation"),
    ("Path Robotics",      "C", "greenhouse", "pathrobotics",   "https://www.path-robotics.com/careers", "Hardware/Robotics · autonomous welding"),
    ("Agility Robotics",   "C", "greenhouse", "agilityrobotics","https://www.agilityrobotics.com/careers", "Hardware/Robotics · humanoid logistics"),
    ("Apptronik",          "C", "greenhouse", "apptronik",      "https://apptronik.com/careers", "Hardware/Robotics · humanoids"),
    ("Collaborative Robotics","C","ashby",    "cobot",          "https://www.collaborativerobotics.com/careers", "Hardware/Robotics · cobots; early-stage"),
    ("Formlabs",           "C", "greenhouse", "formlabs",       "https://careers.formlabs.com/", "Hardware · 3D printing"),
    ("Markforged",         "C", "greenhouse", "markforged",     "https://markforged.com/careers", "Hardware · industrial 3D printing"),

    # ── Athlete / Outdoor (you're the user — passion bets) ───────────────
    ("Peloton",            "C", "greenhouse", "peloton",        "https://www.onepeloton.com/careers", "Athlete/Hardware · connected fitness"),
    ("Zwift",              "C", "greenhouse", "zwift",          "https://www.zwift.com/careers", "Athlete · indoor cycling/running; you're the user"),
    ("AllTrails",          "C", "lever",      "alltrails",      "https://www.alltrails.com/careers", "Outdoor · trail app; you're the user (thin board — watch for openings)"),

    # ── Finance / Fintech (optional wedge) ───────────────────────────────
    ("Stripe",             "B", "greenhouse", "stripe",         "https://stripe.com/jobs", "Finance/Platform · payments infra"),
    ("Plaid",              "B", "ashby",      "plaid",          "https://plaid.com/careers/", "Finance · fintech data network"),
    ("Ramp",               "B", "ashby",      "ramp",           "https://ramp.com/careers", "Finance · spend management; fast-growing"),
    ("Brex",               "C", "greenhouse", "brex",           "https://www.brex.com/careers", "Finance · corporate cards/spend"),
    ("Affirm",             "C", "greenhouse", "affirm",         "https://www.affirm.com/careers", "Finance · BNPL"),
    ("Robinhood",          "C", "greenhouse", "robinhood",      "https://careers.robinhood.com", "Finance · retail brokerage"),

    # ── Platform / Product-craft ─────────────────────────────────────────
    ("Notion",             "B", "ashby",      "notion",         "https://www.notion.so/careers", "Platform/Venture · product-craft brand"),
    ("Figma",              "B", "greenhouse", "figma",          "https://www.figma.com/careers/", "Platform/Venture · product-craft brand"),
    ("Vercel",             "C", "greenhouse", "vercel",         "https://vercel.com/careers", "Platform · frontend cloud/devtools"),

    # ════════════════════════════════════════════════════════════════════
    # DISCOVERY ROUND 2 — fitting companies beyond the original board,
    # surfaced 2026-06-12 from APM/MBA-internship programs + domain search.
    # All boards verified live. Many run formal APM/product internships.
    # ════════════════════════════════════════════════════════════════════
    # ── Bullseye new fits (SCM+hardware / athlete / fintech APM) ─────────
    ("Locus Robotics",     "B", "greenhouse", "locusrobotics",  "https://locusrobotics.com/careers/", "SCM&Twins/Hardware · warehouse fulfillment robots — your SCM + embedded fit"),
    ("Eight Sleep",        "B", "ashby",      "eightsleep",     "https://www.eightsleep.com/careers/", "Athlete/Hardware · sleep & recovery; you're the target user"),
    ("Wayve",              "B", "greenhouse", "wayve",          "https://wayve.ai/careers/", "Hardware/AI · embodied AI for driving"),
    ("Sierra",             "B", "ashby",      "sierra",         "https://sierra.ai/careers", "AI&Data · frontier conversational-AI agents (Bret Taylor)"),
    ("Coinbase",           "B", "greenhouse", "coinbase",       "https://www.coinbase.com/careers", "Finance · crypto platform; formal APM program"),
    ("Instacart",          "B", "greenhouse", "instacart",      "https://instacart.careers/", "SCM/Platform · grocery logistics; APM program"),
    ("Airbnb",             "B", "greenhouse", "airbnb",         "https://careers.airbnb.com/", "Platform/Venture · product-craft brand; MBA PM pipeline"),
    ("Block",              "B", "greenhouse", "block",          "https://block.xyz/careers", "Finance · Square/Cash App; large product org"),
    # ── Athlete / health (passion, you're the user) ─────────────────────
    ("Levels",             "C", "ashby",      "levels",         "https://levels.com/careers", "Athlete/Health · metabolic wearables"),
    ("Superpower",         "C", "ashby",      "superpower",     "https://superpower.com/careers", "Health · preventive health platform"),
    ("Future",             "C", "greenhouse", "future",         "https://www.future.co/careers", "Athlete · remote fitness coaching"),
    # ── APM / product-program breadth (strong programs, domain-flex) ────
    ("Pinterest",          "C", "greenhouse", "pinterest",      "https://www.pinterestcareers.com/", "Platform · APM program"),
    ("Dropbox",            "C", "greenhouse", "dropbox",        "https://www.dropbox.com/jobs", "Platform · product org"),
    ("Reddit",             "C", "greenhouse", "reddit",         "https://www.redditinc.com/careers", "Platform · APM program"),
    ("Asana",              "C", "greenhouse", "asana",          "https://asana.com/jobs", "Platform · work-management PM craft"),
    ("Twilio",             "C", "greenhouse", "twilio",         "https://www.twilio.com/en-us/company/jobs", "Platform · developer/comms APIs"),
    ("Lyft",               "C", "greenhouse", "lyft",           "https://www.lyft.com/careers", "Mobility/Platform · APM program"),
    ("Coursera",           "C", "greenhouse", "coursera",       "https://careers.coursera.com/", "Platform/EdTech · learning products"),
    # ── Fintech breadth ─────────────────────────────────────────────────
    ("Chime",              "C", "greenhouse", "chime",          "https://careers.chime.com/", "Finance · consumer fintech"),
    ("Modern Treasury",    "C", "ashby",      "moderntreasury", "https://www.moderntreasury.com/careers", "Finance · payments infra"),
    # ── Hardware / robotics / mobility breadth ──────────────────────────
    ("Archer Aviation",    "C", "greenhouse", "archer",         "https://careers.archer.com/", "Hardware/Mobility · eVTOL aircraft"),
    ("Standard Bots",      "C", "ashby",      "standardbots",   "https://standardbots.com/careers", "Hardware/Robotics · affordable industrial cobots"),
    # ── AI & data breadth ───────────────────────────────────────────────
    ("Writer",             "C", "ashby",      "writer",         "https://writer.com/company/careers/", "AI&Data · enterprise generative AI"),
    ("Baseten",            "C", "ashby",      "baseten",        "https://www.baseten.co/careers/", "AI&Data · ML model serving infra"),
    ("Modal",              "C", "ashby",      "modal",          "https://modal.com/careers", "AI&Data · serverless ML compute"),
]


def seed() -> int:
    db = SessionLocal()
    added = updated = 0
    try:
        for name, tier, ats, token, url, notes in SEED:
            exists = db.scalar(select(Company).where(Company.name == name))
            if exists:
                # Keep verified ATS routing current without clobbering user edits
                # to tier/notes — only repair stale ats_name/ats_token.
                if (exists.ats_name, exists.ats_token) != (ats, token):
                    exists.ats_name = ats
                    exists.ats_token = token
                    updated += 1
                continue
            db.add(Company(name=name, tier=tier, ats_name=ats,
                           ats_token=token, careers_url=url, notes=notes))
            added += 1
        db.commit()
        return added
    finally:
        db.close()


if __name__ == "__main__":
    print(f"seeded {seed()} companies")
