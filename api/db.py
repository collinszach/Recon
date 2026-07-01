"""Database engine, session, and ORM models."""
from datetime import datetime, date
from sqlalchemy import (
    create_engine, String, Integer, Float, Boolean, Text, Date, DateTime,
    ForeignKey, func,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker,
)
from pgvector.sqlalchemy import Vector
from config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    tier: Mapped[str | None] = mapped_column(String, default="B")
    ats_name: Mapped[str | None] = mapped_column(String)
    ats_token: Mapped[str | None] = mapped_column(String)
    careers_url: Mapped[str | None] = mapped_column(String)
    snoozed_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    roles: Mapped[list["Role"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    ats_job_id: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="ats")  # ats | jsearch | usajobs
    title: Mapped[str] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    metro: Mapped[str | None] = mapped_column(String)   # target-metro slug (scan.geo)
    remote_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    department: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)  # full JD text (for scoring + display)
    description_hash: Mapped[str | None] = mapped_column(String)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # from the ATS
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String, default="open")
    # scoring
    fit_score: Mapped[float | None] = mapped_column(Float)
    score_tier: Mapped[str | None] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String)
    why_fit: Mapped[str | None] = mapped_column(Text)
    concerns: Mapped[str | None] = mapped_column(Text)
    curriculum_hook: Mapped[str | None] = mapped_column(Text)
    tc_estimate: Mapped[str | None] = mapped_column(String)
    is_product_pm: Mapped[bool | None] = mapped_column(Boolean)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # user feedback: "up" (good fit) | "down" (not for me) | None — hides downs
    # from the feed and calibrates future scoring toward Zach's actual taste.
    interest: Mapped[str | None] = mapped_column(String)
    interest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # semantic embedding (mxbai-embed-large 1024-dim via gs65 Ollama).
    # is_duplicate: non-ATS role whose embedding is too close to an ATS role
    # at the same company — filtered out of the feed to cut noise.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    company: Mapped["Company"] = relationship(back_populates="roles")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    company_name: Mapped[str | None] = mapped_column(String)
    role_title: Mapped[str | None] = mapped_column(String)
    role_url: Mapped[str | None] = mapped_column(String)
    stage: Mapped[str] = mapped_column(String, default="watching")
    outcome: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action: Mapped[str | None] = mapped_column(String)
    next_action_due: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    role: Mapped["Role | None"] = relationship()


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    from_stage: Mapped[str | None] = mapped_column(String)
    to_stage: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Material(Base):
    """A saved application material — tailored resume, cover letter, outreach, prep.
    role_id/application_id are SET NULL on delete so materials survive re-scans."""
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String)               # resume | cover_letter | outreach | prep | note
    title: Mapped[str | None] = mapped_column(String)       # e.g. "Anduril — Software PM, Air Defense"
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    kind: Mapped[str | None] = mapped_column(String)         # recruiter|phone|technical|behavioral|onsite|final
    scheduled_at: Mapped[date | None] = mapped_column(Date)
    interviewer: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String)      # pending|passed|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    application: Mapped["Application"] = relationship()


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    company: Mapped[str | None] = mapped_column(String)          # free-text company name
    name: Mapped[str | None] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    linkedin: Mapped[str | None] = mapped_column(String)
    warmth: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, default="to_reach")  # to_reach|sent|replied|met
    last_touch: Mapped[date | None] = mapped_column(Date)
    next_touch: Mapped[date | None] = mapped_column(Date)
    last_outreach: Mapped[str | None] = mapped_column(Text)      # last drafted/sent message
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanRun(Base):
    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    companies_scanned: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_count: Mapped[int] = mapped_column(Integer, default=0)
    searched: Mapped[bool] = mapped_column(Boolean, default=False)  # did this run hit the search providers?
    claude_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    claude_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    errors: Mapped[str | None] = mapped_column(Text)


class DailyBrief(Base):
    __tablename__ = "daily_briefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    brief_date: Mapped[date] = mapped_column(Date, unique=True)
    markdown: Mapped[str | None] = mapped_column(Text)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    action_count: Mapped[int] = mapped_column(Integer, default=0)
    reminders_sent: Mapped[bool] = mapped_column(Boolean, default=False)  # once/day gate
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(String, unique=True)
    p256dh: Mapped[str] = mapped_column(String)
    auth: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Resume(Base):
    """Single-row master resume profile (id=1). Experiences live in ResumeExperience."""
    __tablename__ = "resume"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String)
    headline: Mapped[str | None] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[str | None] = mapped_column(Text)
    education: Mapped[str | None] = mapped_column(Text)
    links: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), onupdate=func.now())


class ResumeExperience(Base):
    __tablename__ = "resume_experiences"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String, default="work")   # work | project | leadership
    company: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    start_date: Mapped[str | None] = mapped_column(String)
    end_date: Mapped[str | None] = mapped_column(String)
    bullets: Mapped[str | None] = mapped_column(Text)          # newline-separated
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
