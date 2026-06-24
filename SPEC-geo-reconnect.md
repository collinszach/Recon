# SPEC — Reconnect + Geo-Targeting (2026-06-24)

Two tracks the user raised as one ("it's offline and not scraping; want more jobs in my
metros"). Diagnosis showed the backend is **healthy and scraping** — both are really
client/feature work, not an outage.

## Diagnosis (verified live 2026-06-24)
- `http://100.91.198.28:8010/health` → `{"status":"ok","scoring_mode":"live"}`.
- `/api/scan/runs` → scans every 3h, last 09:07 UTC, 90 companies (24 new / 13 changed).
  **Scraping works.** Not offline.
- Public `recon.zacharyjcollins.com` → 302 to Cloudflare Access OTP. The iOS app (`.auto`
  in `ios/Recon/Config.swift`) tries Tailscale `:8010` then the tunnel; off-Tailnet the
  tunnel is the only path and Access blocks it (no service token wired) → "offline."
- `location` is stored on `Role` (`api/db.py`) and parsed by every ATS parser, but is
  **never filtered, boosted, or surfaced by geography** anywhere. Track filtering
  (`intern_filter.py`) is title-only. So metro roles are largely already scraped, just
  unscored/unsurfaced.

---

## Track 1 — Reconnect (decision: CF Access service token)

Keep Access (OTP) on the dashboard; give the native app a service token.

1. **Cloudflare** (user runs via `!`, interactive): Zero Trust → Access → Service Auth →
   create token "recon-ios"; add it to the Recon application's Access policy (Include →
   Service Token).
2. **App**: paste Client-Id / Client-Secret into Settings (fields already exist:
   `SettingsView.swift` §"Cloudflare Access"; headers wired in `Config.authorize`). Set
   endpoint to Tunnel (or leave Auto — token now lets the tunnel candidate succeed).
3. **Hardening** (code):
   - `ReconAPI`/`Config`: treat a 302 or `text/html` response as **Access-blocked**, not
     "online" — distinct error copy ("add a service token in Settings") vs. true
     unreachable.
   - `.auto` failure message names which candidate failed and why.

Acceptance: with token set and phone **off** Tailscale, Roles/Today load over the tunnel.

---

## Track 2 — Geo-targeting (decision: surface + filter + company expansion)

Target metros: **Charleston SC · NYC metro · DC/NoVA/MD · SoCal (LA/OC/SD/Irvine) ·
Boston · PA (Philly/Pittsburgh)** + Remote-US.

### 2a. Metro taxonomy — `api/scan/geo.py` (new, pure stdlib)
- `metro_of(location: str|None) -> str|None` mapping location strings to a metro slug via
  regex (city + state + common aliases; e.g. "New York", "NYC", "Manhattan", "Brooklyn",
  "Jersey City" → `nyc`). Remote-US handled separately (`remote`).
- Unit-tested like `intern_filter` (no app context needed).

### 2b. Persist metro — `Role.metro` column + reconcile
- `api/db.py`: add `metro: Mapped[str|None]`. Migration note: additive nullable column;
  backfill existing rows in `db/` init or a one-off. **Hard-stop before any destructive
  migration per CLAUDE.md** — additive only.
- `scan/reconcile.py`: set `metro = metro_of(f.location)` on insert/update.

### 2c. Surface in scoring — `scan/runner.py`
- Add a **metro lane**: roles in a target metro AND in a tracked title class get scored
  even if per-track caps would otherwise drop them (dedup against existing lanes).
- Pass metro into the scorer prompt (`claude_scorer.py` §LOCATION) as a soft positive
  signal — these are relocation-friendly, not penalized as "remote/elsewhere."

### 2d. API + app facet
- `/api/roles?metro=nyc` (and `metro` in the JSON payload — `main.py:84`).
- iOS Roles tab: metro segment/filter alongside the existing Internships/Full-time split.

### 2e. Company expansion (discovery round 3) — `api/seed/companies.py`
- Research + **live-verify ATS tokens** (the seed file's invariant: every token hits a
  non-empty public board) for employers concentrated in the target metros. Candidate
  themes: Charleston/DC defense & gov-tech & SaaS; Boston robotics/biotech/enterprise;
  NYC fintech/media/commerce; SoCal aero/hardware; PA health/industrial.
- Tier per the existing rubric; note metro in the description. `seed()` self-heals.
- This is the lever that materially raises raw job **count** in these metros.

Acceptance: `/api/roles?metro=charleston` returns roles; new metro companies appear in
`/api/companies` and contribute to the next scan's totals; app can browse by city.

---

## Out of scope
Auto-apply, login-walled scraping, changed scan cadence, defense-exclusion rubric rework
(tracked separately in CLAUDE.md).

## Build order
1. Track 1 reconnect (token + app hardening) — restores the user's access immediately.
2. Track 2a–2d geo surfacing — ships the facet over already-scraped data.
3. Track 2e company expansion — discovery/verification round, additive.
