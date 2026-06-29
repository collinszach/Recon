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

    # ─── Focus: which tracks to scan/score ──────────────────
    # "intern"   -> only internships          "fulltime" -> only full-time PM roles
    # "both"     -> internships + full-time product-management roles (default)
    track_mode: str = "both"
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
    search_metros_only: bool = True          # keep only results in a target metro / US-remote
    search_max_queries_per_run: int = 12     # hard cap on provider calls per run (quota guard)
    search_max_pages: int = 1                # JSearch pages per term (10 results/page)
    search_date_posted: str = "week"         # JSearch: all|today|3days|week|month
    search_max_results_per_query: int = 50   # USAJobs ResultsPerPage cap
    search_terms: str = ""                   # comma-separated override; blank -> derived from tracks
    jsearch_api_key: str = ""                # RapidAPI key for jsearch.p.rapidapi.com
    usajobs_api_key: str = ""                # data.usajobs.gov Authorization-Key
    usajobs_email: str = ""                  # USAJobs requires a contact email as the User-Agent

    scan_hour_local: int = 6
    scan_interval_hours: int = 3        # how often the worker runs the scan
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


settings = Settings()
