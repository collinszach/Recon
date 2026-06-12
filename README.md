# Recon

Self-hosted job-application tracker + autonomous role scanner. Polls your target companies'
job boards daily, scores new roles against your profile with Claude, tracks every application,
and serves your career dashboard as the front page. Built for a Beelink NUC.

## Quickstart

```bash
cp .env.example .env
#   set ANTHROPIC_API_KEY
#   leave SCORING_MODE=stub to run free; switch to "live" for real Claude scoring
docker compose up --build
```

Then open **http://localhost:8000/** — the dashboard. The **● Recon Feed** tab goes live once
the API is up. Trigger the first scan from that tab's "Run scan now" button, or:

```bash
curl -X POST http://localhost:8000/api/scan/run
```

## What runs
- **db** — Postgres 16 + pgvector
- **redis** — queue/cache
- **api** — FastAPI: REST + serves the dashboard (`:8000`)
- **worker** — APScheduler, fires the daily scan at `SCAN_HOUR_LOCAL`

## Free dev mode
`SCORING_MODE=stub` runs the entire pipeline — fetch, reconcile, brief, pipeline — with a
heuristic scorer and **zero API spend**. Flip to `live` when you want real fit scoring.

## Daily flow
1. Worker wakes at 06:00 local.
2. Each non-snoozed company's ATS JSON endpoint is fetched (polite delays, descriptive UA).
3. Roles are reconciled: new / changed / closed.
4. New + changed roles are scored against your profile.
5. A single Markdown brief is written and shown on the Recon Feed tab.

## MCP
`python -m mcp.server` (inside the api image) exposes Recon's tools so Claude can drive it:
"what's new today?", "move the Samsara app to screen", "add a company". See `CLAUDE.md`.

## First-run checklist
- [ ] Set `ANTHROPIC_API_KEY` in `.env`
- [ ] Verify ATS slugs in `api/seed/companies.py` (some are best-effort guesses)
- [ ] Put Cloudflare Access in front of the tunnel before exposing publicly
- [ ] Keep `SCORING_MODE=stub` until you've confirmed scans look right, then go `live`

See `SPEC.md` for the full design and `CLAUDE.md` for the operating manual.
