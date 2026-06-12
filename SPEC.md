# Recon — Job Application Tracker & Autonomous Role Scanner

**Version:** 1.0.0
**Owner:** Zach Collins
**Target host:** Beelink NUC (Intel N95, 16GB DDR4)
**Status:** Spec — ready for Director kickoff
**Supersedes:** Recon CLI v2.0.0 (this absorbs and extends it)

---

## 0. One-paragraph summary

Recon is a self-hosted application that maintains a live database of open roles at a curated target-company list, scans those companies' career sites and job boards once daily, surfaces new and changed postings, and tracks every application Zach submits through a Kanban pipeline. A Claude-powered synthesis layer scores each new role against Zach's profile, drafts tailored outreach, and produces a single daily brief. It runs entirely on the Beelink NUC behind a Cloudflare Tunnel, with all LLM work routed to the Claude API because the hardware cannot host a local model.

---

## 1. Goals & non-goals

### Goals
- **Single source of truth** for every open role worth tracking and every application in flight.
- **Daily autonomous scan** of target companies' ATS endpoints — no manual checking.
- **Change detection**, not just discovery: catch new postings, closed postings, title/comp/location edits.
- **Fit scoring** of each new role against Zach's profile and the dashboard tiers.
- **Application pipeline** (Kanban) with stage history, contacts, follow-up reminders.
- **One daily brief** — what's new, what changed, what needs action — delivered to one place.
- **Runs unattended** on the NUC within its memory/CPU envelope.

### Non-goals (v1)
- No auto-applying. Recon surfaces and drafts; Zach submits. (Auto-submit is an explicit prohibited action and a good way to get an account flagged.)
- No CAPTCHA solving or login-walled scraping. Public endpoints only.
- No local LLM. The N95 + 16GB cannot run anything useful; all synthesis is Claude API.
- No mobile-native app. PWA is sufficient (matches your Argus pattern).

---

## 2. Architecture

Mirrors your existing self-hosted stack so it slots into the NUC cleanly.

```
┌─────────────────────────────────────────────────────────────┐
│  Beelink NUC (Intel N95, 16GB)  ·  Docker Compose            │
│                                                              │
│  ┌────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │ Next.js    │   │ FastAPI      │   │ Worker (APScheduler│  │
│  │ PWA (UI)   │◄─►│ API + MCP    │◄─►│ or Celery+Redis)   │  │
│  │ :3000      │   │ server :8000 │   │ daily scan jobs    │  │
│  └────────────┘   └──────┬───────┘   └─────────┬──────────┘  │
│                          │                     │             │
│                   ┌──────▼─────────────────────▼──────────┐  │
│                   │ PostgreSQL 16 + pgvector               │  │
│                   │ (roles, applications, companies, runs) │  │
│                   └────────────────────────────────────────┘  │
│                   ┌────────────────────────────────────────┐  │
│                   │ Redis (job queue, scan locks, cache)   │  │
│                   └────────────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │ Cloudflare Tunnel
                           ▼
                 recon.zacharyjcollins.com  (Cloudflare Access in front)
                           │
        ┌──────────────────┼──────────────────────┐
        ▼                  ▼                       ▼
   Claude API        ATS public APIs          Optional MCP clients
  (fit scoring,    (Greenhouse, Ashby,       (Claude Desktop / other
   brief, drafts)   Lever, Workday)           agents hit Recon's MCP)
```

### Why these choices
- **No local model:** the N95 tops out well below what even a 7B quantized model needs to be useful. Route 100% of synthesis to Claude API. Budget below.
- **APScheduler over Celery** for v1 — a single daily cron-style job doesn't justify Celery's overhead on 16GB. Promote to Celery+Redis only if you parallelize heavy scraping.
- **pgvector** so the daily brief can dedupe near-identical reposts and let you semantic-search past roles ("that fleet PM role from March").

---

## 3. The two faces of Recon: it's an MCP server AND it uses MCP

You asked for MCP — there are two distinct roles and v1 should be clear about both.

### 3a. Recon AS an MCP server (primary)
Recon exposes its own tools over MCP so that **Claude (Desktop, or any agent you run) can drive it conversationally.** This is the high-value direction: you open Claude, say "what's new in my pipeline today and draft a follow-up to the Samsara recruiter," and it calls Recon's tools.

**Tools Recon exposes:**
| Tool | Purpose |
|---|---|
| `list_open_roles(tier?, company?, since?)` | Query the current open-role table |
| `get_daily_brief(date?)` | Return the synthesized brief for a date |
| `get_application(id)` / `list_applications(stage?)` | Pipeline reads |
| `update_application(id, stage, note?)` | Move a card, log a note |
| `add_role_manually(url)` | Fetch + parse a one-off posting you found |
| `score_role(role_id)` | Run/refresh fit scoring on demand |
| `draft_outreach(role_id, contact?, tone?)` | Generate tailored outreach copy |
| `snooze_company(name, days)` / `add_company(name, ats_url)` | Manage the target list |

This is a standard MCP server (Python SDK, stdio or SSE transport). Because you run Claude in this surface, you may already have a connector slot for it.

### 3b. Recon USING MCP / external connectors (secondary)
Recon's own synthesis calls can use connectors you already have wired — e.g. dropping the daily brief into a Google Doc, creating Google Calendar follow-up reminders, or filing application notes in Airtable. Keep this optional and behind a feature flag; the brief works fine as a PWA page + push without any of it.

> **Note on the "check websites daily" mechanism.** The reliable way to read most modern ATS career pages is **their JSON endpoints, not HTML scraping.** Greenhouse, Ashby, Lever, and Workday all expose structured job data. That's what Recon hits. A headless-browser fallback (Playwright) exists only for the handful of companies with no API, and it runs sparingly because Playwright on the N95 is the single heaviest thing in the system.

---

## 4. Data sources & the daily scan

### 4a. ATS parsers (build order — same as your CLI plan)
1. **Greenhouse** — `https://boards-api.greenhouse.io/v1/boards/{token}/jobs` — clean public JSON. Many of your targets (Databricks-adjacent, lots of startups) use it.
2. **Ashby** — `https://api.ashbyhq.com/posting-api/job-board/{org}` — public posting API. Common at newer Series B–D companies (Mercury, etc.).
3. **Lever** — `https://api.lever.co/v0/postings/{org}?mode=json` — public JSON.
4. **Workday** — per-tenant JSON POST endpoint (`/wday/cxs/{tenant}/{site}/jobs`). Heavier, paginated, tenant-specific. The big-tech and large-cap targets (Microsoft, NVIDIA, Apple, Rivian) mostly live here.
5. **Playwright fallback** — only for no-API career pages. Rate-limited, runs last.

Each parser implements one interface:

```python
class ATSParser(Protocol):
    ats_name: str
    def fetch(self, company: Company) -> list[RawPosting]: ...
    def normalize(self, raw: RawPosting) -> Role: ...
```

### 4b. The daily run (one APScheduler job, ~06:00 local)
```
for company in target_companies where not snoozed:
    raw = parser.fetch(company)            # JSON endpoint, polite delay
    roles = [parser.normalize(r) for r in raw]
    diff = reconcile(roles, db_state)      # new / changed / closed
    persist(diff)
score_new_and_changed_via_claude()         # batch, one API call per ~10 roles
brief = synthesize_daily_brief()           # single Claude call
deliver(brief)                             # PWA + web push (+ optional Doc/email)
record_run_metrics()                       # for the cost & health dashboard
```

**Politeness / not-getting-blocked rules (hard requirements):**
- One company at a time, randomized 2–5s delay between requests, descriptive User-Agent with your contact.
- Respect `robots.txt` and rate limits; exponential backoff on 429/503.
- Cache aggressively — only re-fetch a company once per day unless you force-refresh.
- No login-walled content, no CAPTCHA bypass, no aggressive parallelism. This keeps you on the right side of ToS and keeps the N95 cool.

---

## 5. Fit scoring (Claude API)

Each new/changed role gets scored once, then cached. The prompt carries:
- **Zach's profile block** — the dashboard's "why this profile is rare" assets, the four priority domains, the curriculum mapping.
- **The tier rubric** — S/A/B definitions, the $200K TC floor, WLB weighting, the commercial-first / no-exclusively-government rule.
- **The role JSON.**

Output (strict JSON, parsed and stored):
```json
{
  "fit_score": 0-10,
  "tier": "A|B|C|pass",
  "domain": "AI&Data|SCM&Twins|Hardware|Venture|Finance|Platform|other",
  "why_fit": "≤2 sentences, specific to the JD",
  "concerns": "≤1 sentence or null",
  "curriculum_hook": "which course(s) this role justifies",
  "tc_estimate": "range or null",
  "is_pm_product_not_program": true
}
```

`is_pm_product_not_program` enforces your rule that "PM" must mean product, not program/project management. Anything failing it auto-drops to a "review" lane rather than the main feed.

---

## 6. Application pipeline (the tracker)

Kanban board, stages:

`Watching → Drafting → Applied → Screen → Onsite → Offer → Closed (won/lost/withdrawn)`

Each card stores: role snapshot (frozen at apply time, since postings vanish), company, fit score, contacts, stage history with timestamps, next-action + due date, outreach drafts, and free-form notes. Follow-up reminders fire as web-push (and optional calendar events). A role discovered by the scanner becomes a pipeline card with one tap.

---

## 7. Data model (core tables)

```sql
companies(id, name, tier, ats_name, ats_token, careers_url,
          snoozed_until, notes, created_at)

roles(id, company_id, ats_job_id, title, location, remote_flag,
      department, url, description_hash, first_seen, last_seen,
      status,                       -- open | changed | closed
      fit_score, tier, domain, why_fit, concerns, curriculum_hook,
      tc_estimate, is_product_pm, embedding vector(1536))

applications(id, role_id, stage, applied_at, next_action,
             next_action_due, outcome, created_at, updated_at)

application_events(id, application_id, from_stage, to_stage, note, at)

contacts(id, company_id, name, role, email, linkedin, warmth, notes)

scan_runs(id, started_at, finished_at, companies_scanned,
          new_count, changed_count, closed_count,
          claude_tokens_in, claude_tokens_out, est_cost_usd, errors)

daily_briefs(id, date, markdown, new_count, action_count, created_at)
```

`description_hash` drives change detection; `embedding` drives dedupe + semantic search.

---

## 8. The daily brief

One Markdown document per day, rendered in the PWA and pushed. Structure:

```
# Recon — {date}
**{N} new · {M} changed · {K} need action**

## Needs your action
- Follow-ups due, offers pending, stale "Applied" cards >10 days

## New roles worth your time   (fit ≥ 7, sorted)
- [Company] Title — fit 9.2 · $TC · why_fit · [Track] [Draft outreach]

## Changed
- [Company] Title — was Senior PM, now Group PM · comp edited

## Closed since yesterday
- (so you stop chasing dead postings)

## Pipeline snapshot
- Watching 4 · Applied 6 · Screen 2 · Onsite 1 · Offer 0
```

Generated by one Claude call over the day's diff + pipeline state.

---

## 9. Hardware budget (the N95 constraint is real)

| Component | Idle RAM | Notes |
|---|---|---|
| Postgres + pgvector | ~300–500MB | fine |
| Redis | ~50MB | fine |
| FastAPI + MCP | ~200MB | fine |
| Next.js (prod build, not dev) | ~150MB | **serve built, never `next dev`** |
| APScheduler worker | ~150MB | spikes during scan |
| Playwright (fallback only) | ~400MB **per browser** | the danger — cap at 1 instance, kill after use |
| **Headroom** | | leaves ~13GB; comfortable if Playwright is rare |

Rules baked into the spec: Chromium launches one-at-a-time and is torn down immediately; the daily scan is sequential, not parallel; Next.js runs as a production build. With those, this sits well inside 16GB.

---

## 10. Claude API cost estimate

- ~15 target companies → ~10–40 new/changed roles on an active day, far fewer most days.
- Fit scoring: batch ~10 roles/call. Brief: 1 call/day. Outreach drafts: on demand.
- Typical day: **3–6 calls**, a few thousand tokens each.
- **Estimate: ~$0.30–0.80/day → ~$10–20/month**, in line with your other projects' budgets. The cost dashboard (`scan_runs`) tracks it live so it never surprises you.

---

## 11. Security & access

- **Cloudflare Access** in front of the tunnel — only your identity reaches the app. No public auth surface to harden.
- Secrets (Claude key, ATS tokens) in a `.env` excluded via `.claudeignore`, never committed.
- MCP server bound to localhost; if exposed over SSE, it sits behind the same Cloudflare Access policy.
- No storing of credentials for any job site — Recon never logs into anything on your behalf.

---

## 12. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| **0 — Skeleton** | Docker Compose, Postgres, FastAPI health check, one company seeded | `docker compose up` serves `/health` |
| **1 — Greenhouse + model** | Greenhouse parser, roles table, reconcile/diff logic | daily scan of GH companies populates roles |
| **2 — Scoring + brief** | Claude fit scoring, daily brief generation, PWA brief page | a real brief renders for a real scan |
| **3 — Pipeline** | Kanban UI, applications + events, reminders | you can track an app end-to-end |
| **4 — More parsers** | Ashby, Lever, Workday, Playwright fallback | big-tech targets covered |
| **5 — MCP server** | Recon's tools exposed over MCP, wired to Claude | "what's new today?" works conversationally |
| **6 — Connectors (opt)** | Brief → Google Doc, follow-ups → Calendar, notes → Airtable | behind feature flags |

Phases 0–3 are the usable core. 4–6 are leverage.

---

## 13. Seed company list

Pull tiers straight from the master dashboard:

- **Tier A:** Samsara, Microsoft, Apple, Databricks, Rivian, NVIDIA
- **Tier B:** Google Cloud, Celonis, Waymo, Mercury, Procore, Meta Reality Labs
- **Tier C:** onX Maps, Oura, Strava, Sonos, Boston Dynamics, WHOOP

First task in Phase 1 is resolving each to its ATS + token (mostly a one-time lookup of which board software each uses).

---

## 14. Open questions for kickoff

1. **Delivery surface for the brief** — PWA + web push only, or also email / a Google Doc? (Push is enough to start.)
2. **Outreach drafting** — keep it on-demand via MCP, or auto-draft for every fit-≥8 role and stage it? (On-demand is cheaper and less noisy.)
3. **Workday depth** — full coverage of the big-cap targets in Phase 4, or treat Workday companies as manual-add until they prove worth the parser effort?
4. **Reuse Recon CLI** — fold the existing v2.0.0 parsers in as the starting point, or rebuild clean against this schema?

---

*Recon turns the master plan's company board into a living system: it watches the roles so you don't have to, scores them the way you would, and keeps every application honest — all on hardware you already own, for the price of a couple coffees a month.*
