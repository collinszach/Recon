"""Seed the master resume from zacharyjcollins.com / collinszach/resume (RESUME.MD).
Idempotent: only runs if the resume table is empty, so user edits are never clobbered."""
from sqlalchemy import select
from db import SessionLocal, Resume, ResumeExperience

PROFILE = dict(
    full_name="Zach Collins",
    headline="Builder PM · Engineering ↔ Product · Berkeley Haas '28",
    location="Encinitas, CA",
    summary=(
        "A product manager with an engineering core. I build, ship, and optimize the products I "
        "manage — from enterprise data platforms to projects I run on my own home lab. Hardware to "
        "software, spec sheet to production.\n\n"
        "A mechanical engineer who became a PM by shipping real things: roadmap, backlog, and "
        "production deployments for enterprise data platforms at Deloitte for three years. I use AI "
        "and automation to cut friction out of my own work and think in systems, whether the problem "
        "is an enterprise platform or a consumer app built over a weekend. Incoming MBA/MEng at "
        "Berkeley Haas, headed for platform PM roles where technical depth and systems thinking both "
        "carry weight."
    ),
    skills=(
        "Product: product strategy, PRDs, roadmaps, backlog management, stakeholder alignment, UAT/QA\n"
        "Technical: AWS, GCP, Python, SQL, GitHub, SAP EWM/TM, Power BI, Jira, ServiceNow, MBSE (SysML), ETL/data pipelines, AI-assisted development\n"
        "Certifications: AWS Solutions Architect Associate, GCP Professional Cloud Architect, CompTIA Security+"
    ),
    education=(
        "UC Berkeley — MBA (Haas School of Business) + MEng (College of Engineering), Berkeley, CA — May 2028\n"
        "Virginia Tech — B.S. Mechanical Engineering, Summa Cum Laude, GPA 3.87, Blacksburg, VA — May 2023"
    ),
    links="zacharyjcollins.com · github.com/collinszach",
)

# (kind, company, title, location, start, end, [bullets], sort_order)
EXPERIENCES = [
    ("work", "Deloitte Consulting LLP",
     "Software Engineer II / Technical Product Manager — AI & Platform Systems",
     "Arlington, VA", "Aug 2023", "Present", [
        "Engineer and de facto product owner for SAP EWM/TM platforms running a mission-critical federal supply chain; owned roadmap, PRDs, backlog, UAT/QA, and release planning across four live applications",
        "Shipped 100+ production releases, improving reliability, throughput, and adoption across the supply-chain platform",
        "Built an AI-assisted Python migration tool that cut warehouse record-migration time 94%, plus an ETL certification pipeline deployed to AWS — integrating multiple data sources and migrating millions of records",
        "Led the use-case workstream for an MBSE digital-twin initiative (SysML in Cameo) on a defense Smart MRO facility, standing up a working additive-manufacturing simulation",
     ], 0),
    ("work", "Deloitte Consulting LLP", "Strategy & Analytics Summer Scholar",
     "San Diego, CA", "Jun 2022", "Jul 2022", [
        "Product Manager for an internal collaboration platform built on SharePoint and Microsoft Teams",
        "Defined requirements, aligned stakeholders, prioritized features, and led rollout to cross-functional delivery teams",
     ], 1),
    ("work", "Collins Aerospace (Raytheon Technologies)", "Program Engineering Intern",
     "Santa Fe Springs, CA", "May 2021", "Aug 2021", [
        "Supported net-new and remanufactured aerospace hardware programs, contributing to drawing validation, quality reviews, and lean manufacturing analysis",
     ], 2),
    ("project", "Modular Laser Scanning System", "Technical Lead",
     None, None, None, [
        "Designed and built a modular trailer-based laser scanning system; owned architecture and data pipeline for roadway condition monitoring",
        "Reduced required scanning volume ~90% through system-level redesign and data optimization",
        "Prototyped pipelines in Python with AI-assisted development and optimized performance-critical I/O in C++ to improve disk bandwidth 10x",
     ], 3),
    ("leadership", "ACE Mentor Program of America", "Lead Mentor",
     "Arlington, VA", "Sep 2024", "May 2026", [
        "Led mentors and students through a year-long engineering capstone; team placed 2nd regionally",
     ], 4),
]


def seed() -> int:
    db = SessionLocal()
    try:
        if db.scalar(select(Resume).limit(1)):
            return 0  # already seeded; never clobber edits
        db.add(Resume(id=1, **PROFILE))
        for kind, co, title, loc, start, end, bullets, order in EXPERIENCES:
            db.add(ResumeExperience(kind=kind, company=co, title=title, location=loc,
                                    start_date=start, end_date=end,
                                    bullets="\n".join(bullets), sort_order=order))
        db.commit()
        return 1 + len(EXPERIENCES)
    finally:
        db.close()


if __name__ == "__main__":
    print(f"seeded resume rows: {seed()}")
