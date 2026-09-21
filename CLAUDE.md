# CLAUDE.md — Recon

Operating manual for Claude Code when working in this repo. Read fully before acting.

## What this is
Recon is a self-hosted job-application tracker + autonomous role scanner. It polls target
companies' ATS JSON endpoints once daily, scores new/changed roles against Zach's profile via
the Claude API, tracks applications through a Kanban pipeline, and serves a master career
dashboard as its front page. Runs on a Beelink NUC (Intel N95, 16GB) under Docker Compose
behind a Cloudflare Tunnel. See `SPEC.md` for the full spec.

## Session State
- **Phase:** Deployed & running. Greenhouse/Ashby/Lever/Workday parsers, model, scan, stub
  scorer, brief, MCP server, worker, and the live dashboard are in place and live on the NUC.
- **2026-08-15 — critical fix + cost/frequency/push/startups build:**
  - **Fixed a 10-day pipeline outage.** `search_runner.py`'s TheMuse ingest hit a duplicate-key
    IntegrityError; `runner.py` caught it but never rolled back the session, so the *next* DB
    call crashed the whole scan before scoring/brief/alerts ran. Every ~12h run from 2026-08-05
    to 2026-08-15 died there (`scan_runs.finished_at` stayed NULL, no `daily_briefs` row). Fixed
    with per-row ats_job_id pre-check + try/flush/rollback in both `search_runner.py` insert
    paths, plus a defensive `db.rollback()` in `runner.py`'s search-ingest except. Deployed +
    verified a clean end-to-end run.
  - **Scoring cost: batching, not caching.** First tried Anthropic prompt caching
    (`llm.complete(..., cache_system=True)`), but verified empirically on the deployed
    container that it doesn't help here: Claude Haiku 4.5's minimum cacheable prompt length is
    ~4096 tokens (binary-searched: 4010 tokens → no cache, 4510 → cache hit), and the scoring
    rubric is only ~1.5-2.6K tokens depending on lens — never crosses the threshold, so
    `cache_creation_input_tokens`/`cache_read_input_tokens` stayed 0 on every real scoring call.
    `llm.py`'s `cache_system` plumbing is left in place (harmless, may help future longer
    prompts) but scoring no longer passes it. Switched to literal batching instead:
    `claude_scorer.BATCH_SIZE = 10` — `_score_live` groups roles by lens, chunks each lens into
    batches, and sends one call per batch (`BATCH_INSTRUCTIONS`, JSON array response) so the
    rubric is paid once per ~10 roles instead of once per role. A malformed/length-mismatched
    batch response falls back to scoring that batch's roles individually (`_score_one`) rather
    than silently dropping any of them. `PRICING` in `claude_scorer.py` still carries cache-rate
    tuples for if/when a future rubric grows past the cache threshold.
  - **Scan cadence decoupled from cost.** `scan_interval_hours` default 12 → 1 (config.py) —
    now cheap to run hourly since scoring only touches the new/changed delta each cycle and is
    cache-discounted. Search ingest keeps its own once/day gate (`SEARCH_INTERVAL_HOURS`,
    unchanged) inside the same `run_daily_scan()`.
  - **Native iOS push (APNs).** New `notify/apns.py` — 4th delivery channel (provider-token JWT
    auth, ES256, signed with a `.p8` key) alongside push/email/gdoc, wired into all three
    `deliver_*` functions in `notify/deliver.py`. New `device_tokens` table + `POST /api/push/
    register-device`. Config: `NOTIFY_APNS_ENABLED`, `APNS_KEY_PATH/KEY_ID/TEAM_ID/BUNDLE_ID`,
    `APNS_USE_SANDBOX` — all blank/false by default (no-ops, like every other notify channel).
    **Not yet activated** — needs Zach's Apple Developer `.p8` auth key mounted into the
    container and the four APNS_* vars set. iOS side (`PushManager.swift`, `ReconApp.swift`
    delegate, `Recon.entitlements` via `project.yml`, `ReconAPI.registerDevice`) is built and
    compiles clean (`xcodebuild ... BUILD SUCCEEDED`) — registers for remote notifications on
    launch and POSTs the device token, ready the moment APNs is turned on server-side.
  - **Startups tracker** (fintech / defense / sustainability-energy / product-tech-data) — new
    feature, separate from the job-scan `Company`/`Role` pipeline. `Startup` + `StartupContact`
    tables (`db.py`, `db/init.sql`); `api/startups/researcher.py` generates an on-demand cached
    writeup (`POST /api/startups/{id}/writeup`, Sonnet-tier `claude_model`, never runs on a
    schedule) and runs warm-path contact research (`POST /api/startups/{id}/contacts/research`,
    mirrors `resume/networking.py` — never invents named people). Full CRUD at `/api/startups`.
    **Deliberately no background/recurring discovery scan** — LLM cost is only spent when Zach
    adds a startup or explicitly asks, to avoid cost creep. iOS: new `StartupsView.swift` +
    `Startups` tab in `ContentView.swift`, builds clean.
  - **Deployed and verified same day** — hourly cadence confirmed live (`worker up — scan
    scheduled every 1 hour(s)`), multiple clean scan_runs on record. **APNs still not
    activated** — needs Zach's Apple Developer `.p8` key. The `aps-environment` entitlement was
    **removed from `project.yml`** (not just unregistered) after it blocked on-device
    `xcodebuild` installs with "doesn't include the Push Notifications capability" — that
    registration can only happen via the Xcode GUI (Signing & Capabilities → + Capability) or
    the Developer Portal, never from a headless build. `PushManager.swift`'s
    `registerForRemoteNotifications()` call is harmless without the entitlement (silently hits
    `didFailToRegister`). Re-add the entitlement block to `project.yml` (see git history,
    2026-08-15) once Zach has enabled the capability through Xcode himself.
- **2026-08-15 (later same day) — intern-only pivot + rule-based scoring + startups seed:**
  Zach's explicit call, in order: (1) drop full-time/ops/tech scoring, intern-only everywhere;
  (2) score every internship found, no cap, but **never through the LLM** — rules only, to keep
  cost at zero; (3) filter internships by MBA-track and by company sector; (4) seed the startups
  tracker now AND run it as ongoing weekly discovery (reversing the earlier "on-demand only, no
  background scanning" decision below — that constraint is superseded for startups specifically).
  - `TRACK_MODE` default (and server `.env`) → `intern`. `score_max_intern` cap removed
    entirely — internship scoring costs nothing, so there's no reason to cut the list short.
  - **New: `scoring/claude_scorer._score_intern_rules`** — fully deterministic (MBA-track +
    company tier + role-type keyword + off-cycle term match), zero AI cost. `score_roles()` now
    routes every internship through this unconditionally; only non-intern roles (dormant while
    `TRACK_MODE=intern`) would still hit Claude. Tried Anthropic prompt caching for this first
    (see the batching entry above) — irrelevant here since there's no AI call at all to cache.
  - **New: `scan.intern_filter.is_mba_track`** (`Role.is_mba` column) — matches bare "MBA"
    anywhere in the title (broadest reliable signal; catches "MBA Summer Intern", "Rotational
    MBA Program", any word order) plus "summer associate" and APM-program titles.
  - **New: `seed/sectors.py`** — keyword-based `Company.sector` classifier (big_tech | finance |
    defense_aerospace | consulting; unmatched stays `None` → "other"). Backfilled on every API
    boot (`_backfill_sector`, same idempotent pattern as `_backfill_metro`) and applied at
    auto-company-creation time in `search_runner.py`. `/api/sectors` facet endpoint;
    `/api/roles?sector=&mba=` filters. iOS: sector Menu + MBA toggle in `RolesView.swift`, "MBA"
    pill on matching cards.
  - **16 MBA-recruiting employers added** to `seed/companies.py` (Goldman Sachs, JPMorgan,
    Morgan Stanley, McKinsey, BCG, Bain, Deloitte, Accenture, PepsiCo, P&G, General Mills,
    Target, Ford, GM, UnitedHealth, Delta) — the original 145-company list skewed tech/product/
    hardware and surfaced **zero** MBA-track internships. Verified (2026-08-15) this is a real
    seasonal gap, not a bug: TheMuse sweep pulled 65 real postings from 5 of these employers
    same-day, all full-time — MBA Summer Associate programs for the Summer 2027 cohort Zach
    targets typically post Sept-Nov, several months out. Will surface automatically once posted.
  - **Startups: bulk-seeded 40 companies** via new `startups.researcher.discover_candidates` /
    `run_discovery` (`POST /api/startups/discover?n=`), each with a full writeup + up to 3
    auto-persisted contact personas (108 contacts total, 36/40 startups). **Ongoing weekly
    discovery is live** — `worker/scheduler.py` `discovery_job`, gated by
    `STARTUP_DISCOVERY_ENABLED`/`STARTUP_DISCOVERY_BATCH` (default 6/week). This is real
    recurring AI cost, unlike everything else added today — Zach's explicit, informed call.
  - **Two more latent bugs found and fixed while doing this work** (both now deployed):
    1. `scan/runner.py`'s main per-company ATS loop never rolled back the DB session on error —
       identical bug class to the 2026-08-05→15 outage above, different call site. A deadlock
       (triggered by *this session's own* concurrent debugging queries) exposed it; now fixed
       the same way (`db.rollback()` in the except block).
    2. `startups/researcher._parse_json_block` only handled JSON *objects*; the new discovery
       feature returns an *array* and was getting corrupted by the object-shaped fallback
       trimming. Also: `max_tokens=1100` on both the startup and the **pre-existing** role-based
       "who to reach out to" contact research (`resume/networking.py`) was empirically found to
       truncate mid-JSON on every real call — raised to 2000 in both places.
  - **Lesson reinforced twice this session:** `docker compose restart <svc>` does NOT pick up
    code changes — both `worker/Dockerfile` and `api/Dockerfile` `COPY` source in at build time.
    Always `docker compose build <svc> && docker compose up -d --no-deps <svc>` (or full
    `--build`) after an rsync, or the "fix" silently keeps running the old image.
- **2026-09-21 — new arrivals visible on Today; passed-on roles stay gone:**
  - **Unscored arrivals were invisible.** `/api/roles` defaults `scored_only=true`
    (`scored_at IS NOT NULL`), so a posting the scan had just ingested but the scorer
    hadn't graded yet never reached the app at all. On top of that the client's
    `Store.feed` did `($0.tier ?? "pass") != "PASS"` — a nil tier means *unscored*, not
    rejected, so even if one had arrived the feed threw it away. Both fixed: new
    `include_unscored` param on `/api/roles` admits unscored rows whose `first_seen` is
    within `NEW_ARRIVAL_DAYS` (7) **in addition to** scored ones, the iOS `roles()` call
    passes it, and `feed` only drops an explicit `PASS`. The week bound matters — without
    it this would pull the entire dormant non-intern backlog (never scored while
    `TRACK_MODE=intern`, tens of thousands of rows carrying JD text). Default stays
    `false`, so every other caller is unchanged.
  - **Down-voted roles came back on every cold launch.** `feed` filtered on
    `hiddenRoleIds`, the in-memory optimistic set, which `init()` rebuilds *only from the
    offline queue* — and that queue by construction holds just the ratings that FAILED to
    send. A rating the server accepted left no trace locally, so on relaunch the cached
    `roles` payload (written before the rating) showed it as unrated and it reappeared.
    Offline it reappeared permanently, since no refresh could land to correct it. Now
    `feed` goes through `interest(of:)` (which also reads the role's server-recorded
    `interest`), and `hiddenRoleIds`/`likedRoleIds` are persisted to `Cache` on every
    rating and unioned back at launch. This is the 2026-09-18 offline-ratings fix finished
    properly — that pass persisted the *queue*, not the *state*.
  - `TodayView`'s "New today" shows 10 (was 5) with a "+N more in Roles" tail.
  - Server query semantics verified against SQLite (scored ∪ recent, no backlog, no
    down-voted, no duplicates, no closed). **iOS changes are unbuilt** — no Swift
    toolchain in the session container, and the NUC is unreachable without Tailscale, so
    nothing here is deployed or run on device yet.
- **Deployed:** `zach@100.91.198.28` (Tailscale), `~/recon`, via
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`. The NUC is shared,
  so the prod overlay publishes **only the API on host port 8010** (8000/6379 were taken) and
  keeps Postgres/Redis internal to the compose network. Health: `http://100.91.198.28:8010/health`.
- **Company list:** 85 companies, every ATS slug verified live (see `api/seed/companies.py`).
  18 dashboard targets + 42 profile additions + 25 discovery-round-2 (APM programs + domain
  fits like Locus Robotics, Eight Sleep, Coinbase, Wayve, Sierra). `seed()` self-heals stale ats.
- **Track mode — `intern` only as of 2026-08-15** (was `both`; see Session State below for the
  full pivot). `api/scan/intern_filter.py` still classifies is_internship / is_fulltime_pm / etc.
  and the FULLTIME_PROFILE/OPS_PROFILE Claude rubrics below still exist and still work — they're
  just dormant while `TRACK_MODE=intern`, not deleted. Internships are no longer capped
  (`score_max_intern` removed) and no longer LLM-scored (see `_score_intern_rules`). `/api/roles`
  still returns a `track` field. **Rubric loosened 2026-06-28** (see Hard rules, applies to the
  dormant full-time/ops lenses): background-fit-based, industry-neutral, soft comp,
  role-type-broad — the old non-product A/B clamp in `_apply` was removed. `is_product_pm` is an
  informational tag only (no longer caps the tier).
- **Search sources (2026-06-28):** beyond per-company ATS endpoints, Recon can pull cross-employer
  postings from third-party aggregators — **JSearch** (RapidAPI Google-for-Jobs, incl. LinkedIn) and
  **USAJobs** (federal). `api/search/` (provider per file + registry); `api/scan/search_runner.py`
  upserts a `Company` per employer, geo-filters to target metros, dedupes by title (ATS wins), and
  INSERTS without closing (search is a sampled slice). Wired into `run_daily_scan` **gated to once/
  day** (`SEARCH_INTERVAL_HOURS`) to respect free tiers; off unless `SEARCH_ENABLED=true` + keys set.
  `Role.source` (`ats|jsearch|usajobs`) marks provenance; auto-created companies are tier B,
  `ats_name=<provider>`. NOT scraping LinkedIn directly (respects the hard rule) — these are APIs.
- **iOS app:** `ios/` — **native SwiftUI** (Today / Internships / Pipeline / Résumé / Plan),
  generated by XcodeGen. Roles tab segments Internships vs Full-time. Talks to the REST API;
  supports a CF Access service token. Installed on the iPhone 17 Pro (team K28M38H7Y5). Radar icon.
- **Resume + tailoring:** `Resume`/`ResumeExperience` tables (seeded from zacharyjcollins.com /
  collinszach/resume). CRUD at `/api/resume`; `POST /api/roles/{id}/tailor` returns a Claude
  match analysis (score, strengths, gaps, keywords, tailored summary, bullets; suggestions only,
  ~$0.02/call). Résumé tab edits it; "Tailor my résumé to this role" sheet on role detail.
- **Defense is in scope (settled 2026-06-24):** the scorer rubric explicitly ranks
  defense/national-security PRODUCT roles on merit as a *strength* (federal supply chain, MBSE on
  a defense Smart MRO, Collins/Raytheon) — NOT a downgrade. Anduril is seeded tier A and scores A
  live. The earlier "downgrade defense / exclude Anduril" heads-up is obsolete; don't re-add it.
  Reinforced by the target metros (Charleston, DC/NoVA) which lean defense/gov-tech. `domain`
  enum includes both `Defense` and `Aerospace`.
- **Access model (2026-06-24):** **Local/Tailscale-only.** The iOS app talks straight to
  `http://100.91.198.28:8010` over Tailscale; the public Cloudflare Tunnel + Access + service
  token were **removed** (the `cloudflared` sidecar is stripped from `docker-compose.prod.yml`,
  which is now an empty overlay). Don't re-add a public tunnel unless off-Tailnet/shared access
  is explicitly needed.
- **Geo targeting (2026-06-24, expanded 2026-07-07):** `api/scan/geo.py` tags each role with a
  target-metro slug (Charleston / NYC / DC-NoVA-MD / SoCal / Boston / PA / Raleigh-Durham-RTP /
  SF-Bay-Area / Remote-US). RTP is scoped to the Raleigh-Durham-Chapel Hill-Cary corridor (not
  statewide NC); the Bay Area metro is the full Bay (SF/Oakland/San Jose/Peninsula), not just SF
  proper; VA/MD stay folded into the existing DC-NoVA-MD metro (no separate statewide VA/MD
  metros). `Role.metro` column (added
  via idempotent startup `ALTER` + one-time backfill in `main.py`). `runner.py` has a **metro
  lane** that scores target-metro roles in our tracks even past per-track caps
  (`score_max_metro`). Scorer treats a `TARGET METRO` as a positive (relocation-friendly).
  `/api/roles?metro=` filter + `/api/metros` facet; iOS Roles tab has a metro menu.
- **Next up:** discovery round 3 — add employers concentrated in the target metros (Charleston/DC
  gov-tech & defense, Boston robotics/biotech, NYC fintech, SoCal aero/hardware, PA health/
  industrial), each with a **live-verified** ATS token. Also: wire Microsoft/Apple/Google/Meta/
  Rivian (proprietary/iCIMS — Playwright or manual add); populate pgvector embeddings.
- **Materials & networking (iOS):** per-role vault saves tailored résumé / outreach / cover
  letter / interview prep; "Who to reach out to" researches target personas (warm-path first,
  never invented names) with openers + LinkedIn search + one-tap add-to-CRM; PDF export of any
  saved material via the system share sheet. Backend: `resume/{cover,networking}.py`, `Material`
  model, `/api/materials`, `/api/roles/{id}/{cover_letter,networking}`.

## Architecture Decisions
1. **Pluggable LLM backend (`LLM_PROVIDER`).** The N95 can't host an LLM, so synthesis runs
   off-box. `LLM_PROVIDER=anthropic` (default) → Claude API; `LLM_PROVIDER=local` → **gs65**, an
   Ollama host on the Tailnet (`http://100.119.105.2:11434/v1`, OpenAI-compatible), which is free.
   All call sites go through `api/llm.py` (`llm.complete(system, messages, max_tokens)` →
   `.text/.tokens_in/.tokens_out`); no module talks to a vendor SDK directly. `SCORING_MODE=stub`
   still runs the whole pipeline free with a heuristic scorer; `live` calls whichever backend is set.
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
- Scoring rubric (`api/scoring/claude_scorer.py`), loosened 2026-06-28 — keep it this way unless
  Zach says otherwise: **background-fit-based, not title-gated** (product AND adjacent — TPM,
  technical program/project, solutions, BizOps/strategy, GM, eng-adjacent all score on merit);
  **industry-neutral** (domain is a filter tag, never a weight); **soft comp** (~$200K+ target,
  higher better, but never a hard tier cap); **technology/innovation is a positive signal**;
  WLB-weighted; seniority still caps (he's early-career). Do NOT re-add the product-only A/B clamp
  or the hard $200K floor. `is_product_pm` is an informational tag only.
- Predict-before-act: before editing, state what you expect to change and why. Surgical edits,
  conventional commits, hard stop before anything destructive (DB drops, migrations).

## Run
```bash
cp .env.example .env          # set ANTHROPIC_API_KEY; SCORING_MODE=stub to start free
docker compose up --build     # db + redis + api + worker (local: api on :8000)
# dashboard:  http://localhost:8000/
# health:     http://localhost:8000/health
curl -X POST http://localhost:8000/api/scan/run   # trigger a scan now
```

On the NUC (shared host — API on :8010, db/redis stay internal):
```bash
ssh zach@100.91.198.28 'cd ~/recon && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d'
curl http://100.91.198.28:8010/health
```

## Layout
```
db/init.sql              schema (pgvector)
api/main.py              FastAPI: REST + serves dashboard
api/db.py                SQLAlchemy models + engine
api/config.py            settings (.env)
api/parsers/             greenhouse | ashby | lever | workday (per-company ATS, +registry)
api/search/              jsearch | usajobs (cross-employer aggregators, +registry)
api/scan/search_runner.py  ingest search results: upsert company, geo-filter, dedupe, insert
api/llm.py               unified LLM client (anthropic | local gs65) — all AI calls route here
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
- [x] Verify every `ats_token` in the seed list — done 2026-06-12, all 60 hit live.
- [x] Workday parser — built; NVIDIA/Procore/Sonos/Boston Dynamics wired. (Microsoft/Apple/
      Google/Meta run proprietary in-house ATS with no public board — still `manual`.)
- [x] ~~Cloudflare Tunnel → `recon.zacharyjcollins.com`~~ — dropped 2026-06-24; Local/Tailscale-only.
- [x] Flip `SCORING_MODE=live` — done; NUC runs live (`/health` reports `scoring_mode: live`),
      daily scans score against the API (~$0.01/run). Cover-letter + networking AI features are live.
- [ ] Web-push for the daily brief (PWA service worker; VAPID keys in `.env`).
- [ ] pgvector embeddings for dedupe + semantic search (column exists, not yet populated).
- [ ] Optional connectors: brief → Google Doc, follow-ups → Calendar (behind a flag).
- [ ] Rivian (iCIMS) — needs a dedicated parser or manual add; no public JSON board.
