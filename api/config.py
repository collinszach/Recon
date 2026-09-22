"""Central config — reads from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://recon:recon@db:5432/recon"
    redis_url: str = "redis://redis:6379/0"

    # ─── LLM backend ────────────────────────────────────────
    # "anthropic" -> Claude API (cloud)   "local" -> gs65, an Ollama host on the Tailnet
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"      # résumé/cover/interview features (quality-sensitive, rare)
    scoring_model: str = "claude-haiku-4-5"      # bulk daily role scoring (~3x cheaper than Sonnet)
    # gs65: local LLM served by Ollama over Tailscale (OpenAI-compatible /v1 API).
    local_llm_base_url: str = "http://100.119.105.2:11434/v1"
    local_llm_model: str = "gs65"
    local_llm_api_key: str = "ollama"   # Ollama ignores the value but the client needs one
    scoring_mode: str = "stub"          # "stub" | "live"
    # Master switch for the LLM fit-scorer. False (2026-09-21, Zach's call):
    # Recon is a tracker now — what's new, what I applied to, what I never want
    # to see again — not a ranking engine. The scorer, its lanes and its caps
    # stay in the tree, and fit_score/score_tier/why_fit keep their old values in
    # the DB, so flipping this back on is all that's needed to resume scoring.
    # Relevance is the title classifier instead (scan.intern_filter).
    scoring_enabled: bool = False

    # ─── Focus: which tracks to scan/score ──────────────────
    # "intern"   -> only internships          "fulltime" -> only full-time PM roles
    # "both"     -> internships + full-time product-management roles
    # Default "intern" (2026-08-15, Zach's call) — internships are scored free via
    # rules (see scoring/claude_scorer.py._score_intern_rules), not Claude, so this
    # keeps the pipeline's AI spend near zero while still surfacing everything.
    track_mode: str = "intern"
    intern_target_year: int = 2027      # the summer term being targeted
    score_max_intern: int = 200         # cost cap: max internships scored per scan
    score_max_fulltime: int = 200       # cost cap: max full-time PM roles scored per scan
    score_max_ops: int = 150            # cost cap: max ops/strategy roles scored per scan
    score_max_tech: int = 150           # cost cap: max adjacent-tech (TPM/solutions/SWE/data) per scan
    score_max_metro: int = 150          # cost cap: max extra target-metro roles per scan
    # back-compat: if intern_only is set true it forces track_mode="intern"
    intern_only: bool = False

    # ─── Search sources (third-party job aggregators) ───────
    # JSearch (Google-for-Jobs via RapidAPI, incl. LinkedIn) + USAJobs (federal).
    # Search is keyword+geo (cross-employer), so it runs OUTSIDE the per-company ATS
    # loop, auto-creates a Company per employer, and is gated to once/day to respect
    # the providers' free tiers. Roles are geo-filtered to the target metros.
    search_enabled: bool = False
    search_interval_hours: int = 24          # run search at most this often (free-tier friendly)
    # False (2026-08-16, Zach's call): ingest every location, not just the 9 curated
    # target metros — the state facet (scan.geo.state_of) covers everywhere, filter client-side.
    search_metros_only: bool = False
    search_max_queries_per_run: int = 12     # hard cap on provider calls per run (quota guard)
    search_max_pages: int = 1                # JSearch pages per term (10 results/page)
    search_date_posted: str = "week"         # JSearch: all|today|3days|week|month
    search_max_results_per_query: int = 50   # USAJobs ResultsPerPage cap
    search_terms: str = ""                   # comma-separated override; blank -> derived from tracks
    # Company sweep: proprietary/bot-walled employers (ats_name='jsearch_company') have no public
    # ATS board, so instead of a per-site parser we run ONE employer-scoped JSearch query each and
    # file the hits under that known company. Capped + round-robined by day to respect the free tier.
    # Raised 6 -> 25 (2026-08-16): the jsearch_company pool grew to ~70+ companies
    # (Fortune 500 + MBA-recruiting sweep) — at 6/day that was a ~12-day rotation
    # before every employer got checked even once. Search itself still runs at
    # most once/day (SEARCH_INTERVAL_HOURS), so this only affects how many
    # employers get swept within that one daily run, not query frequency.
    search_company_sweep_max: int = 25       # employer-scoped queries per run (rotates across days)
    jsearch_api_key: str = ""                # RapidAPI key for jsearch.p.rapidapi.com
    themuse_enabled: bool = True             # The Muse (themuse.com) — free, no key needed
    themuse_api_key: str = ""                # optional free key to raise the 500/hr limit
    # Adzuna (2026-08-16) — broad cross-board aggregator, meaningfully wider long-tail
    # coverage than JSearch/TheMuse (regional/smaller employers). Free signup:
    # https://developer.adzuna.com/overview — enabled once both keys are set.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "us"
    usajobs_api_key: str = ""                # data.usajobs.gov Authorization-Key
    usajobs_email: str = ""                  # USAJobs requires a contact email as the User-Agent

    # ─── Semantic embeddings (pgvector dedup + search) ─────
    # Calls the Ollama OpenAI-compat /v1/embeddings on gs65 with mxbai-embed-large.
    # embed_enabled=False skips all embedding work (safe to disable for local dev).
    embed_enabled: bool = True
    embed_model: str = "mxbai-embed-large:latest"
    embed_base_url: str = "http://100.119.105.2:11434/v1"
    embed_dim: int = 1024
    embed_batch_size: int = 32
    # Cosine similarity above this threshold marks a JSearch/USAJobs role as a
    # near-duplicate of an ATS role at the same company (ATS is always canonical).
    embed_dedup_threshold: float = 0.93

    scan_hour_local: int = 6
    # Scan (ATS fetch + reconcile) is cheap — no LLM calls, just HTTP. Scoring only
    # runs against the new/changed delta each cycle, and prompt caching (see
    # scoring/claude_scorer.py) makes back-to-back scoring calls ~90% cheaper on
    # input tokens, so an hourly cadence keeps postings fresh without materially
    # raising cost over the old 12h interval (2026-08-15).
    scan_interval_hours: int = 1        # how often the worker runs the scan
    notify_min_fit: float = 7.0         # min fit_score for a new-role alert
    scan_min_delay_sec: float = 2.0
    scan_max_delay_sec: float = 5.0
    scan_user_agent: str = "ReconJobTracker/1.0"
    tz: str = "America/Los_Angeles"

    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # ─── Notifications: web push ────────────────────────────
    notify_push_enabled: bool = False
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:zakslax@gmail.com"

    # ─── Gmail: know when someone replies ───────────────────
    # Read-only (gmail.readonly): Recon can read mail and cannot send or delete
    # it. Chosen over an app password because the NUC is a shared machine and an
    # app password grants full mailbox control; this scope is also revocable on
    # its own from the Google account.
    #
    # The refresh token is minted once, on Zach's Mac, by scripts/gmail_auth.py
    # — that keeps the OAuth redirect on localhost where Google allows plain
    # http, so the API never has to host a callback or be publicly reachable.
    mail_enabled: bool = False
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    mail_lookback_days: int = 60          # how far back a poll looks
    mail_max_messages: int = 60           # cap per poll (quota + N95 politeness)

    # ─── Notifications: email ───────────────────────────────
    notify_email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    # ─── Notifications: Google Doc ──────────────────────────
    notify_gdoc_enabled: bool = False
    gdoc_credentials_json: str = ""
    gdoc_folder_id: str = ""

    # ─── Startups tracker: ongoing discovery ────────────────
    # Weekly (not hourly, unlike the job scan) since this is real recurring AI
    # cost (2026-08-15, Zach's explicit call — "seed now, but do ongoing
    # discovery"). n new startups/week, each gets a writeup + contact research.
    startup_discovery_enabled: bool = True
    startup_discovery_batch: int = 6

    # ─── Notifications: native iOS push (APNs) ──────────────
    # Provider-token auth (ES256 JWT signed with a .p8 auth key from the Apple
    # Developer account) — no per-device certs, one key covers every app/device.
    notify_apns_enabled: bool = False
    apns_key_path: str = ""       # path to the AuthKey_XXXX.p8 file, mounted into the container
    apns_key_id: str = ""         # the "XXXX" in AuthKey_XXXX.p8
    apns_team_id: str = ""        # Apple Developer team ID
    apns_bundle_id: str = ""      # e.g. com.zacharyjcollins.Recon — also used as the apns-topic
    apns_use_sandbox: bool = False  # true for Xcode dev/ad-hoc builds not from TestFlight/App Store


settings = Settings()
