"""Recon MCP server — exposes tools so Claude can drive the tracker.

Run standalone (stdio transport):
    python -m mcp.server
Then add to your Claude Desktop / agent MCP config pointing at this process.

Tools:
    list_open_roles, get_daily_brief, list_applications,
    update_application, add_company, add_role, run_scan
"""
import json
from datetime import date
from sqlalchemy import select
from db import SessionLocal, Company, Role, Application, DailyBrief

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - lets the file import even if mcp missing
    FastMCP = None


server = FastMCP("recon") if FastMCP else None


def _register():
    @server.tool()
    def list_open_roles(tier: str | None = None, min_fit: float = 0.0,
                        scored_only: bool = True) -> str:
        """List currently-open roles, optionally filtered by tier (A/B/C) and minimum fit score.
        In internship mode only scored (= internship) roles are returned by default; pass
        scored_only=false to browse the full set."""
        db = SessionLocal()
        try:
            q = select(Role).where(Role.status.in_(["open", "changed"]))
            if scored_only:
                q = q.where(Role.scored_at.isnot(None))
            rows = db.scalars(q.order_by(Role.fit_score.desc().nullslast())).all()
            out = []
            for r in rows:
                co = r.company
                if tier and co and co.tier != tier:
                    continue
                if r.fit_score is not None and r.fit_score < min_fit:
                    continue
                out.append({"company": co.name if co else None,
                            "title": r.title, "fit": r.fit_score,
                            "tc": r.tc_estimate, "url": r.url, "why": r.why_fit})
            return json.dumps(out[:40], indent=2)
        finally:
            db.close()

    @server.tool()
    def get_daily_brief(d: str | None = None) -> str:
        """Return the daily brief markdown for a date (YYYY-MM-DD), or the latest."""
        db = SessionLocal()
        try:
            target = date.fromisoformat(d) if d else date.today()
            b = db.scalar(select(DailyBrief).where(DailyBrief.brief_date == target))
            if not b:
                b = db.scalar(select(DailyBrief).order_by(DailyBrief.brief_date.desc()))
            return b.markdown if b else "No brief yet. Run a scan."
        finally:
            db.close()

    @server.tool()
    def list_applications(stage: str | None = None) -> str:
        """List pipeline applications, optionally filtered by stage."""
        db = SessionLocal()
        try:
            q = select(Application)
            if stage:
                q = q.where(Application.stage == stage)
            rows = db.scalars(q).all()
            return json.dumps([{"id": a.id, "company": a.company_name,
                                "title": a.role_title, "stage": a.stage,
                                "next_action": a.next_action} for a in rows], indent=2)
        finally:
            db.close()

    @server.tool()
    def update_application(app_id: int, stage: str | None = None, note: str | None = None) -> str:
        """Move an application to a new stage and/or append a note."""
        db = SessionLocal()
        try:
            a = db.get(Application, app_id)
            if not a:
                return f"application {app_id} not found"
            if stage:
                a.stage = stage
            if note:
                a.notes = (a.notes + "\n" if a.notes else "") + note
            db.commit()
            return f"updated application {app_id} -> stage={a.stage}"
        finally:
            db.close()

    @server.tool()
    def add_company(name: str, ats_name: str, ats_token: str, tier: str = "B") -> str:
        """Add a company to the target list (ats_name: greenhouse|ashby|lever|manual)."""
        db = SessionLocal()
        try:
            if db.scalar(select(Company).where(Company.name == name)):
                return f"{name} already tracked"
            db.add(Company(name=name, ats_name=ats_name, ats_token=ats_token, tier=tier))
            db.commit()
            return f"added {name} ({ats_name}:{ats_token})"
        finally:
            db.close()

    @server.tool()
    def add_role(company: str, title: str, url: str | None = None,
                 location: str | None = None, description: str | None = None) -> str:
        """Manually add a single role found on a proprietary board that no parser
        or the JSearch sweep reached. Creates the company if unknown, geo-tags,
        and scores it inline so it surfaces immediately."""
        from datetime import date
        from sqlalchemy import func
        from db import Role
        from scan.geo import metro_of
        from parsers.base import NormalizedRole
        from scoring.claude_scorer import score_roles
        db = SessionLocal()
        try:
            co = db.scalar(select(Company).where(func.lower(Company.name) == company.strip().lower()))
            if co is None:
                co = Company(name=company.strip(), tier="B", ats_name="manual",
                             notes=f"auto-added via MCP add_role {date.today()}")
                db.add(co)
                db.flush()
            nr = NormalizedRole(ats_job_id=f"manual:{url or title}", title=title,
                                location=location, description=description or "")
            if db.scalar(select(Role).where(Role.company_id == co.id,
                                            Role.ats_job_id == nr.ats_job_id)):
                return f"role already tracked for {co.name}"
            role = Role(company_id=co.id, ats_job_id=nr.ats_job_id, source="manual",
                        title=nr.title, location=nr.location, metro=metro_of(nr.location),
                        remote_flag=nr.remote_flag, url=url, description=nr.description or None,
                        description_hash=nr.description_hash, status="open")
            db.add(role)
            db.flush()
            score_roles(db, [role])
            db.commit()
            return (f"added {role.title} @ {co.name} "
                    f"(metro={role.metro}, tier={role.score_tier}, fit={role.fit_score})")
        finally:
            db.close()

    @server.tool()
    def run_scan() -> str:
        """Trigger a full scan now (fetch, reconcile, score, brief)."""
        from scan.runner import run_daily_scan
        return json.dumps(run_daily_scan(), indent=2)


if server:
    _register()


def main():
    if not server:
        raise SystemExit("mcp package not installed")
    server.run()


if __name__ == "__main__":
    main()
