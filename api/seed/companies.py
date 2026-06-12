"""Seed the target-company list from the master dashboard.

ats_token values were verified by hitting each public ATS endpoint directly
(see notes per-company for anything left as 'manual').
Set ats_name='manual' for any company whose ATS isn't wired yet.

Workday tokens use the format "{tenant}:{dc}:{site}", matching
api/parsers/workday.py (e.g. "nvidia:wd5:NVIDIAExternalCareerSite").
"""
from sqlalchemy import select
from db import SessionLocal, Company

# (name, tier, ats_name, ats_token, careers_url, notes)
SEED = [
    # ── Tier A ───────────────────────────────────────────────
    ("Samsara",            "A", "greenhouse", "samsara",        "https://www.samsara.com/company/careers", None),
    ("Databricks",         "A", "greenhouse", "databricks",     "https://www.databricks.com/company/careers", None),
    ("Rivian",             "A", "manual",     None,             "https://careers.rivian.com",
        "Rivian uses iCIMS (internal-careers-rivian.icims.com); no public Greenhouse/Lever/Ashby/Workday board found."),
    ("NVIDIA",             "A", "workday",   "nvidia:wd5:NVIDIAExternalCareerSite", "https://www.nvidia.com/en-us/about-nvidia/careers/", None),
    ("Microsoft",          "A", "manual",     None,             "https://careers.microsoft.com",
        "Microsoft careers.microsoft.com is a proprietary career site, not standard public Workday/Greenhouse/Lever."),
    ("Apple",              "A", "manual",     None,             "https://jobs.apple.com",
        "Apple jobs.apple.com runs a proprietary in-house ATS with no public job-board JSON API."),
    # ── Tier B ───────────────────────────────────────────────
    ("Mercury",            "B", "ashby",      "mercury",        "https://mercury.com/jobs", None),
    ("Celonis",            "B", "greenhouse", "celonis",        "https://www.celonis.com/careers/", None),
    ("Procore",            "B", "workday",   "procore:wd12:Procore_External_Careers", "https://careers.procore.com", None),
    ("Waymo",              "B", "greenhouse", "waymo",          "https://waymo.com/careers/", None),
    ("Google Cloud",       "B", "manual",     None,             "https://careers.google.com",
        "Google careers.google.com is a proprietary in-house ATS; no public Workday/Greenhouse/Lever board."),
    ("Meta Reality Labs",  "B", "manual",     None,             "https://www.metacareers.com",
        "Meta metacareers.com is a proprietary in-house ATS; no public Workday/Greenhouse/Lever board."),
    # ── Tier C ───────────────────────────────────────────────
    ("onX Maps",           "C", "greenhouse", "onxmaps",        "https://www.onxmaps.com/careers", None),
    ("Oura",               "C", "greenhouse", "oura",           "https://ouraring.com/careers", None),
    ("Strava",             "C", "ashby",      "strava",         "https://www.strava.com/careers", None),
    ("Sonos",              "C", "workday",   "sonos:wd1:Sonos", "https://www.sonos.com/careers", None),
    ("Boston Dynamics",    "C", "workday",   "bostondynamics:wd1:Boston_Dynamics", "https://bostondynamics.com/careers/", None),
    ("WHOOP",              "C", "lever",      "whoop",          "https://www.whoop.com/careers/", None),
]


def seed() -> int:
    db = SessionLocal()
    added = 0
    try:
        for name, tier, ats, token, url, notes in SEED:
            exists = db.scalar(select(Company).where(Company.name == name))
            if exists:
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
