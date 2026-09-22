# Where this was left — 2026-09-22

`CLAUDE.md` holds the durable architecture notes. This is the state of play,
what's unverified, and what I'd pick up first.

## What changed since the last handoff

The autofill stopped being "built but unverified" and became "verified, and it
was wrong". Everything below was found by putting real forms in front of it.

**The in-app Fill has now met real forms.** Greenhouse end to end from the Apply
tab, and a signed-in Workday application as far as My Experience.

### What was broken

A live Rocket Lab Greenhouse posting has 40 labelled controls, 5 of them profile
fields. The matcher filled three of the other 35 with confident nonsense:

| Label | Got | Why |
|---|---|---|
| "Are you Hispanic/Latino?" | city | `/city/` matches ethni**city** |
| "Preferred Internship/Co-Op Start Date" | how_heard | `/referr(al\|ed)/` matches P**referred** |
| "Outside of university coursework…" | school | unanchored `/university/` |

The first was a porting regression: `labelFor` concatenated aria-label + name +
id + placeholder, so an input *named* `hispanic_ethnicity` matched on its id.

Four more, each only visible against a live DOM:

- **Workday ships a honeypot.** `name="website"`, 1×1px (0.01px on Mastercard),
  `display:block`, `visibility:visible`, live `offsetParent` — every ordinary
  hidden-field check misses it, and `/\bwebsite\b/` matched it. Autofill would
  have posted a portfolio URL into a bot trap. Present on all three tenants
  sampled, so treat it as standard Workday.
- **react-select's decoy `required` input.** Filling it *satisfies* the browser's
  own validation while nothing is selected, so the form submits with an empty
  Country and no warning. Strictly worse than leaving it alone.
- **Workday's phone row.** Phone Device Type / Country Phone Code / Phone Number
  / Phone Extension — `/\bphone\b/` matched all four.
- **"Preferred First Name"** contains "First Name", and was getting the legal one.

Matching is now tiered (`contact` / `field` / `question`) with word-anchored
patterns. `extension/tests/` runs 78 real labels from six employers through the
matcher **and through the rules lifted out of `AutofillWebView.swift`**, so the
two clients cannot drift again — that drift is what caused the first bug.

### The job descriptions had no structure

Separate from autofill, same shape of bug. Of 85 descriptions in the feed, **3**
contained a single newline. A 6,000-character Rocket Lab posting had 0 newlines
and 59 literal `&nbsp;`, so its headings, paragraphs and bullets ran together.

`parsers/greenhouse.py` turned every tag *and* every newline into a space, and
unescaped once — but Greenhouse double-escapes its `content` (`&lt;div
class=&quot;`), so entities survived tag-stripping and reached the reader. The
function's own comment explained it: *"keep a light text version for
hashing/scoring"*, true until a person started reading it.

`scan/jd_backfill.py` already had a correct block-aware `html_to_text` the
parsers never used. It now lives in `parsers/base.py` as the one implementation.
Also fixed: atlassian joined its sections with a blank line then flattened it
back out, amazon joined with a space, and workday stored `"Malvern, PA 180420"`
— a location and a requisition id — as a description.

Live after deploy: **3 → 52** descriptions with structure, **0** entities, and
the 18 Workday junk descriptions are NULL.

### What now works

**Comboboxes are selected, not deferred.** Greenhouse builds Country, School,
Degree and most questions as react-select. Three non-obvious things:
`el.click()` does nothing (it opens on **mousedown**); mousedown *toggles*, so an
open control must be left alone; and `[role="option"]` is global and lies — a
page with a phone widget holds 244 options before anything is clicked. The
selection diffs against a snapshot taken before the click.

Option matching is exact, then a unique prefix, **and nothing else**. No loose
substring: asked for "Mechanical Engineering" against a list without it, a
substring match returns "Industrial Mechanical Engineering" and nobody notices.
State abbreviations expand first — "CA" substring-matches "North Carolina".

Live on Capital Rx: 8 filled including Country, up from 7 with Country deferred.

## Live numbers at handoff

| | |
|---|---|
| Feed (filtered) | 190 roles |
| Descriptions | 85 of 190; 18 are Workday junk ("Malvern, PA 180420") |
| Fixture | 78 labels, 6 employers, 2 portals |
| Deployed | `4811286` — later commits are docs/extension/iOS only |

## Verified vs not

**Verified against live forms:** the tiered matcher, the honeypot guard (both
Workday adapter passes), combobox select-and-pick on Greenhouse, the profile
editor round-trip, the full-JD fetch, and Workday's My Information step filled
end to end including its dropdowns.

**Not verified:**

- **The Chrome extension has still never met a real form.** Everything above was
  found through the iOS WKWebView filler. The extension shares `field-matcher.js`
  so it inherits the fixes, but its adapters are exercised by nothing.
- **Workday steps 4–7** (Application Questions ×2, Voluntary Disclosures,
  Review). The session expired before reaching them.
- **`adapters/workday.js` was rewired** (2026-09-22) to resolve fields by the
  input `name` first, then the element's own automation id, then a `formField-*`
  id on an ancestor, normalising every spelling onto plain words. 21 identities
  from the live GM form are pinned in the test. **It has not been run against a
  live Workday form since** — the session expired before I could.
- **The tailnet is broken and it is not Recon's fault.** See below.

## The tailnet outage (open, 2026-09-22)

Every real host port on the NUC is unreachable from off-LAN — Recon, atlas and
koastcast alike. Only what tailscaled terminates *itself* answers: SSH, and the
`serve` listener bound to `100.91.198.28:443`. Anything bound to `0.0.0.0`
(nginx :80, recon-api :8010) is dead over the tailnet.

`tcpdump -ni tailscale0 port 8010` proves the packets arrive: SYNs from the Mac
land and retransmit with **no SYN-ACK and no RST**. Silence means a firewall
`DROP` after arrival, not a closed port and not a routing failure.

Ruled out: the tailnet IPv4 (assigned), ufw's config (`Anywhere on tailscale0
ALLOW IN` is present, and an explicit `80 ALLOW IN from 100.0.0.0/8` also fails),
the tailnet ACL (`0.0.0.0/0`, all ports), Docker (plain nginx fails too),
`ShieldsUp` (false), `NetfilterMode` (2), `rp_filter` (2, loose).

Next step is `sudo ufw reload`, then `sudo iptables -vnL INPUT --line-numbers`
and `-vnL ts-input` to see which chain's counters are climbing.

**Workaround that needs no root:** `ssh -N -L 8010:localhost:8010
zach@100.91.198.28`, then point the app's Custom endpoint at
`http://127.0.0.1:8010`. That is how the JD fix was verified in the simulator.

## Gotchas worth keeping

- **Workday search prompts reject typed text.** Setting `.value` fires no search;
  typed-but-uncommitted text is *not* a value and Save clears it. The recipe:
  real keystrokes → pause → **Enter** to search → wait up to ~8s for "Search
  Results (N)" → click the exact row. A partial query returns only category
  headers that look like no results.
- **An expired Workday session looks like a broken form.** Seven opaque
  `VPS|<uuid>` errors, a disabled Save button, and no network request. It is not
  validation. Reload; if you land on Create Account, that was it.
- **Don't trust an impatient read of a slow list.** "GM's school list is empty"
  was wrong — it has "University of California-Berkeley". The search just takes
  longer than a 3-second check.
- **The seed overwrites discovered ATS routing** on every API boot.
- **`ios/Recon.xcodeproj` is generated** — a new `.swift` file is invisible until
  `xcodegen generate`. CI does it; a local build won't.
- **Route order in `api/main.py`**: `/api/roles/{role_id}` is defined last, or it
  shadows `/api/roles/dismissed`.
- **A JS `el.value = x` is discarded by React.** Both fillers write through the
  native value setter — but see above: on Workday's prompts even that is not
  enough.
- **The API startup backfills 51k roles**, so it can take a minute to answer
  after a deploy. That is not a dead service.
- **A PUT of an unknown profile field returns 200 and silently drops it.** "Saved
  but empty on read-back" means the server is behind the code.

## What I'd do next

1. **Fix the tailnet.** It is the only thing actively costing anything, and it
   is broader than this project. See the section above — the diagnosis is done,
   it needs root to finish.
2. **Put the Chrome extension in front of a Greenhouse form.** It is the half of
   the product that has never been tested, it is where the Workday adapters
   live, and it inherited every fix made today without exercising any of them.
3. **Run the rewired Workday adapter against a live form**, next time you are
   genuinely applying and already signed in — not as an exercise.
4. `discipline` is empty in the profile; "Please confirm your City and State"
   still fills only the city.

## Run it

```bash
# deploy (from the Mac, on the tailnet)
ssh zach@100.91.198.28 'cd ~/recon && git pull && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d api worker'

python3 api/tests/test_logic.py              # classifier checks, no DB needed
node extension/tests/test-field-matcher.js   # matcher + iOS port sync
cd ios && xcodegen generate && xcodebuild -project Recon.xcodeproj -scheme Recon \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
```
