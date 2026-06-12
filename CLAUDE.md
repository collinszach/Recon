# CLAUDE.md — Recon

Operating manual for Claude Code when working in this repo. Read fully before acting.

## What this is
Recon is a self-hosted job-application tracker + autonomous role scanner. It polls target
companies' ATS JSON endpoints once daily, scores new/changed roles against Zach's profile via
the Claude API, tracks applications through a Kanban pipeline, and serves a master career
dashboard as its front page. Runs on a Beelink NUC (Intel N95, 16GB) under Docker Compose
behind a Cloudflare Tunnel. See `SPEC.md` for the full spec.

## Session State
- **Phase:** 0→1 scaffold complete. Greenhouse/Ashby/Lever parsers, model, scan, stub scorer,
  brief, MCP server, worker, and the live dashboard tab are in place.
- **Next up:** verify ATS slugs in `api/seed/companies.py`; flip `SCORING_MODE=live`; add the
  Workday parser (Phase 4) for Microsoft/NVIDIA/Apple/Google.

## Architecture Decisions
1. **No local LLM.** The N95 can't host one. All synthesis → Claude API. `SCORING_MODE=stub`
   runs the whole pipeline free with a heuristic scorer; `live` calls the API.
2. **ATS JSON endpoints, not HTML scraping.** Greenhouse/Ashby/Lever have public APIs. Workday
   is per-tenant JSON. Playwright is a last-resort fallback (Phase 4+) — heaviest thing on the
   box, so it runs one browser at a time and is torn down immediately.
3. **APScheduler, not Celery** (one daily job; Celery's overhead isn't justified on 16GB).
4. **Production Next-less front end.** The dashboard is a single static HTML file served by
   FastAPI. No `next dev`. Keeps RAM flat.
5. **No auto-apply.** Recon surfaces and drafts; the human submits. Auto-submit is out of scope
   and a fast way to get an account flagged.

## Hard rules (do not violate)
- Never commit `.env` or any secret. `.claudeignore` lists them.
- Never add login-walled scraping, CAPTCHA solving, or parallel hammering of a career site.
  Respect robots.txt, keep the politeness delay, descriptive User-Agent.
- Never let one company's fetch error kill the whole scan (wrap per-company).
- Keep the scoring profile/rubric in `api/scoring/claude_scorer.py` in sync with the dashboard
  tiers: commercial-first, $200K floor, product-not-program, WLB-weighted.
- Predict-before-act: before editing, state what you expect to change and why. Surgical edits,
  conventional commits, hard stop before anything destructive (DB drops, migrations).

## Run
```bash
cp .env.example .env          # set ANTHROPIC_API_KEY; SCORING_MODE=stub to start free
docker compose up --build     # db + redis + api + worker
# dashboard:  http://localhost:8000/
# health:     http://localhost:8000/health
# trigger a scan immediately:
curl -X POST http://localhost:8000/api/scan/run
```

## Layout
```
db/init.sql              schema (pgvector)
api/main.py              FastAPI: REST + serves dashboard
api/db.py                SQLAlchemy models + engine
api/config.py            settings (.env)
api/parsers/             greenhouse | ashby | lever (+ registry)
api/scan/reconcile.py    new/changed/closed diff
api/scan/runner.py       full daily scan orchestration
api/scoring/             Claude scorer (stub + live)
api/brief/generator.py   daily markdown brief
api/mcp/server.py        MCP tools (Claude drives Recon)
api/seed/companies.py    target list from the dashboard
worker/scheduler.py      APScheduler daily trigger
web/dashboard.html       master plan + live "Recon Feed" tab
```

## MCP
`api/mcp/server.py` exposes `list_open_roles`, `get_daily_brief`, `list_applications`,
`update_application`, `add_company`, `run_scan`. Point a Claude Desktop / agent MCP client at it
(stdio) to drive Recon conversationally. It reads the same DB as the API.

## Known gaps / TODO
- [ ] Verify every `ats_token` in the seed list (some slugs are guesses).
- [ ] Workday parser for Microsoft / NVIDIA / Apple / Google Cloud (currently `manual`).
- [ ] Web-push for the daily brief (PWA service worker).
- [ ] pgvector embeddings for dedupe + semantic search (column exists, not yet populated).
- [ ] Optional connectors: brief → Google Doc, follow-ups → Calendar (behind a flag).
