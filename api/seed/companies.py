"""Seed the target-company list from the master dashboard.

ats_token values are best-effort board slugs and MUST be verified on first run
(Phase 1 task: confirm which board software each company uses + its slug).
Set ats_name='manual' for any company whose ATS isn't wired yet.
"""
from sqlalchemy import select
from db import SessionLocal, Company

# (name, tier, ats_name, ats_token_guess, careers_url)
SEED = [
    # ── Tier A ───────────────────────────────────────────────
    ("Samsara",            "A", "greenhouse", "samsara",        "https://www.samsara.com/company/careers"),
    ("Databricks",         "A", "greenhouse", "databricks",     "https://www.databricks.com/company/careers"),
    ("Rivian",             "A", "greenhouse", "rivian",         "https://careers.rivian.com"),
    ("NVIDIA",             "A", "manual",     None,             "https://www.nvidia.com/en-us/about-nvidia/careers/"),
    ("Microsoft",          "A", "manual",     None,             "https://careers.microsoft.com"),
    ("Apple",              "A", "manual",     None,             "https://jobs.apple.com"),
    # ── Tier B ───────────────────────────────────────────────
    ("Mercury",            "B", "ashby",      "mercury",        "https://mercury.com/jobs"),
    ("Celonis",            "B", "greenhouse", "celonis",        "https://www.celonis.com/careers/"),
    ("Procore",            "B", "greenhouse", "procoretechnologies", "https://careers.procore.com"),
    ("Waymo",              "B", "greenhouse", "waymo",          "https://waymo.com/careers/"),
    ("Google Cloud",       "B", "manual",     None,             "https://careers.google.com"),
    ("Meta Reality Labs",  "B", "manual",     None,             "https://www.metacareers.com"),
    # ── Tier C ───────────────────────────────────────────────
    ("onX Maps",           "C", "greenhouse", "onxmaps",        "https://www.onxmaps.com/careers"),
    ("Oura",               "C", "greenhouse", "oura",           "https://ouraring.com/careers"),
    ("Strava",             "C", "greenhouse", "strava",         "https://www.strava.com/careers"),
    ("Sonos",              "C", "greenhouse", "sonos",          "https://www.sonos.com/careers"),
    ("Boston Dynamics",    "C", "greenhouse", "bostondynamics", "https://bostondynamics.com/careers/"),
    ("WHOOP",              "C", "greenhouse", "whoop",          "https://www.whoop.com/careers/"),
]


def seed() -> int:
    db = SessionLocal()
    added = 0
    try:
        for name, tier, ats, token, url in SEED:
            exists = db.scalar(select(Company).where(Company.name == name))
            if exists:
                continue
            db.add(Company(name=name, tier=tier, ats_name=ats,
                           ats_token=token, careers_url=url))
            added += 1
        db.commit()
        return added
    finally:
        db.close()


if __name__ == "__main__":
    print(f"seeded {seed()} companies")
