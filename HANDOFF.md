# Where this was left — 2026-09-22

Written at the end of a long session. `CLAUDE.md` holds the durable
architecture notes; this is the state of play, what's unverified, and what I'd
pick up first.

## What Recon is now

It stopped being a scorer and became a tracker. The LLM fit-scorer is off
(`SCORING_ENABLED=false`) — the code, the lanes, the caps and the
`fit_score`/`score_tier` columns are all still there, so flipping the flag back
on resumes scoring with nothing to restore. Relevance is now rules:

1. **In-track** — `scan/intern_filter.in_active_track`, internships only under
   `TRACK_MODE=intern`
2. **US only** — `scan/geo.is_us`, with the title as a last-resort signal
3. **Eligible** — `scan/eligibility.eligibility_reason`: PhD-required,
   undergrad-only, existing-clearance
4. **On target** — `scan/eligibility.off_target_reason`: an allowlist of
   product / program / strategy / ops / data / consulting work

Hidden roles keep their reason (`hidden_reason` in the payload,
`/api/roles/hidden-summary` for counts, `show_hidden=true` to see them). That
matters: a filter is only as trustworthy as its false-positive rate.

## Live numbers at handoff

| | |
|---|---|
| Feed (filtered) | ~190 roles, **0.93s**, 179KB |
| Hidden | 459 — 433 off-target, 25 PhD, 1 undergrad-only |
| Pipeline | 9 applied, 26 watching |
| Mail proposals pending | **26**, of which **14 would create applications Recon never knew about** |
| Direct ATS boards | ~155 companies, up from 149 |

## Verified vs not

**Verified against live data:** the feed filters, posting dates (Workday's
relative `postedOn`), backlog flagging (586 roles arrived from three boards
without moving "new today"), dismissals round-trip, Gmail polling and
classification, the thread/awaiting logic (Skydio: "you replied 13 days ago"),
the résumé round-trip (byte-identical), and CI green on all three jobs.

**Not verified — the honest gaps:**

- **Neither autofill has met a real form.** The Chrome extension's Workday
  `data-automation-id` mapping and the in-app WKWebView filler are both
  untested against an actual application. The *mechanisms* are verified (the
  dropdown listbox renders in a portal — 0 options before the click, 19 after;
  the résumé attaches via DataTransfer), the *field mappings* are not.
- **The Apply tab has never been used end to end.** Built and installed, not
  exercised.
- **TransUnion** hasn't been scanned yet (Snyk finally landed +25 roles). Its
  board verified fine when probed directly; it's just late in the scan order.

## What I'd do next

1. **Put a real Greenhouse form in front of the in-app Fill.** It's the only
   place the product might be quietly broken, and one test tells you.
2. **Import the Gmail filters** (`mail/recon-gmail-filters.xml` → Gmail
   Settings → Filters → Import), then set `MAIL_LABEL_FILTER=Recon` so Recon
   reads only what those filters labelled. Neither Recon's `gmail.readonly`
   scope nor the Claude connector can create labels, by design.
3. **Clear the 26 mail proposals** — check the company names on the 14 that
   create applications before accepting; the extraction has been wrong before
   ("Zachary Collins" as an employer).
4. **Follow up with Zoe Downey at Skydio.** 13 days since the thank-you.
5. Amazon's 6 acknowledgements are still pending — one application or six?

## Gotchas worth keeping

- **The seed overwrites discovered ATS routing** on every API boot. It no
  longer downgrades a direct board to an aggregator, but it still wins
  otherwise. Discovery on a seeded company used to last exactly one restart.
- **`ios/Recon.xcodeproj` is generated.** A new `.swift` file is invisible
  until `xcodegen generate` — CI now does this, but a local build won't.
- **Route order in `api/main.py`**: `/api/roles/{role_id}` is defined last on
  purpose, or it shadows `/api/roles/dismissed` and friends.
- **Don't measure correctness only.** The feed loaded all ~25k open roles per
  request for most of the day; every change was checked for correctness and
  none for latency until it became unusable.
- **A JS `el.value = x` is discarded by React.** Both autofills write through
  the native value setter and dispatch `input`/`change`. This is why a form can
  look filled and submit empty.
- **Tailscale SSH re-auth** blocks deploys periodically; it's an interactive
  browser approval, not something to retry around.

## Run it

```bash
# deploy (from the Mac, on the tailnet)
ssh zach@100.91.198.28 'cd ~/recon && git pull && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d api worker'

python3 api/tests/test_logic.py          # classifier checks, no DB needed
cd ios && xcodegen generate && xcodebuild -project Recon.xcodeproj -scheme Recon \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
xcrun devicectl device install app --device 00008150-000268813692401C \
  build/dd/Build/Products/Debug-iphoneos/Recon.app
```
