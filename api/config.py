"""Central config — reads from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://recon:recon@db:5432/recon"
    redis_url: str = "redis://redis:6379/0"

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    scoring_mode: str = "stub"          # "stub" | "live"

    # ─── Focus: which tracks to scan/score ──────────────────
    # "intern"   -> only internships          "fulltime" -> only full-time PM roles
    # "both"     -> internships + full-time product-management roles (default)
    track_mode: str = "both"
    intern_target_year: int = 2027      # the summer term being targeted
    score_max_intern: int = 200         # cost cap: max internships scored per scan
    score_max_fulltime: int = 200       # cost cap: max full-time PM roles scored per scan
    score_max_ops: int = 150            # cost cap: max ops/strategy roles scored per scan
    # back-compat: if intern_only is set true it forces track_mode="intern"
    intern_only: bool = False

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
