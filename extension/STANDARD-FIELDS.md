# The questions that aren't custom

Surveyed 2026-09-21 against live postings, not documentation. The point is to
separate the fields **every** posting on a portal has — which autofill can own —
from the per-employer questions it should hand back to you.

Boards sampled: Rocket Lab, Vannevar Labs, Judi Health and Robinhood
(Greenhouse); Vanguard (Workday).

## Greenhouse

Greenhouse renders almost everything as a react-select **combobox**, including
Country, School and Degree. Typing into one fills its search box without
selecting anything, so autofill matches them and then defers — see
`isCombobox` in `field-matcher.js`.

### Core — on all four boards

| Field | Control | Profile key |
|---|---|---|
| First Name | text | `first_name` |
| Last Name | text | `last_name` |
| Email | text | `email` |
| Phone | tel | `phone` |
| Country | combobox | `country` |
| Resume/CV | file | (attached separately) |
| Cover Letter | file | — |

### Built-in blocks — present when the employer enables them

| Field | Seen on | Profile key |
|---|---|---|
| Preferred First Name | Judi Health | `preferred_name` |
| LinkedIn Profile | Vannevar, Judi Health, Robinhood | `linkedin_url` |
| Website | (Greenhouse built-in) | `portfolio_url` |
| Location (City) / "Please confirm your City and State" | Robinhood, Judi Health | `city` |
| School · Degree · Discipline | Judi Health, Robinhood | `school` `degree` `discipline` |
| Start/End date month + year | Robinhood | — |
| Desired Salary or Hourly Rate | Judi Health | `desired_salary` |
| How did you hear about this opportunity? | Rocket Lab, Vannevar | `how_heard` |

### Work authorisation — different wording, same two questions

Near-universal, and phrased as questions, which is why these keys sit in the
`question` tier:

- "Are you legally authorized to work in the U.S.?" → `work_authorized`
- "Will you now or in the future require Visa sponsorship?" → `requires_sponsorship`

### EEO / self-identification

Greenhouse's standard block is four fields — Gender, Hispanic/Latino, Veteran
Status, Disability Status — but employers frequently replace it with their own
wording ("What is your gender identity?", "How would you describe your
racial/ethnic background?"). Both forms are mapped.

**Deliberately not mapped:** "Are you Hispanic/Latino?" is a yes/no, not a race
category — writing a race value into it would be wrong. Sexual orientation and
transgender identity appear on some boards and Recon doesn't model them.

## Workday

Workday is one product across tenants, so the shape is fixed — six steps:

1. **Create Account / Sign In** — email + password. A hard wall.
2. My Information — name, address, phone, "how did you hear about us", previously employed
3. My Experience — work history, education, skills, résumé, websites, LinkedIn
4. Application Questions — custom, per employer
5. Voluntary Disclosures — gender, ethnicity, veteran, disability, terms
6. Review

**Steps 2–5 could not be surveyed.** They are behind account creation, which is
not something to automate. The field inventory for those steps therefore still
rests on `adapters/workday.js`'s `data-automation-id` map, which remains
unverified against a live form.

### The honeypot — the reason this survey was worth doing

Step 1 ships a bot trap:

```
name="website"  data-automation-id="beecatcher"  1×1 px
label: "Enter website. This input is for robots only, do not enter if you're human."
```

It is `display:block`, `visibility:visible`, `opacity:1`, with a live
`offsetParent` — every ordinary hidden-field check misses it. And `/\bwebsite\b/`
matched it, so autofill would have posted a portfolio URL into a trap whose only
purpose is to identify you as a bot.

Guarded two ways in `field-matcher.js`: `isHoneypot()` (1×1 or smaller, parked
off-canvas, or a trap-shaped name) and `looksLikeTrapText()`, which makes a label
that announces itself as a trap match nothing at all.

## Keeping this honest

`tests/test-field-matcher.js` runs all 67 surveyed labels — including the
honeypot — through the matcher, and again through the rules lifted out of
`ios/Recon/AutofillWebView.swift`, so the two clients cannot drift.
