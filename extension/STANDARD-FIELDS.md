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

Step count and extras vary by tenant:

| | Vanguard | Mastercard | General Motors |
|---|---|---|---|
| Steps | 6 | 7 | 8 |
| Terms checkbox on step 1 | no | yes | no |
| Application Questions | 1 page | 2 pages | 2 pages |
| "Autofill with Resume" | entry choice | entry choice | **step 2, post-auth** |

GM settles what the entry chooser actually means. On the other two, "Autofill
with Resume" and "Apply Manually" look like alternative front doors; GM lists
Autofill with Resume as *step 2 of 8*, after Create Account. The chooser only
picks which path you take **once you are signed in** — there is no résumé-parse
shortcut that skips the account.

Both entry paths — "Apply Manually" and "Autofill with Resume" — land on Create
Account first, so the wall is the product, not the employer. Automating account
creation is off the table; the steps below were surveyed after a human signed in.

### My Information (surveyed on GM, 2026-09-22)

| Field | Control | Profile key |
|---|---|---|
| (previously employed here) | Yes/No radio | — |
| Country / Territory | Workday dropdown | `country` |
| First Name · Last Name | text | `first_name` `last_name` |
| "I have a preferred name" | checkbox, reveals more | `preferred_name` |
| Address Line 1 · Line 2 | text | `address_line1` · — |
| City | text | `city` |
| State | Workday dropdown | `state` |
| Postal Code | text | `zip_code` |
| Phone Device Type | Workday dropdown | `phone_device_type` |
| Country / Territory Phone Code | text | `phone_country_code` |
| Phone Number | text | `phone` |
| Phone Extension | text | `phone_extension` |
| SMS opt-in | checkbox | — |

Four phone-ish fields in a row, and `/\bphone\b/` matched all four — three of
them would have received the phone number. Hence `phone_device_type`,
`phone_extension` and `phone_country_code`: keys with no profile value, matched
*before* `phone`, whose whole job is to claim the label and hand it back.

### `adapters/workday.js` matches on the wrong attribute

The adapter's premise — "Workday's automation ids are stable across tenants" —
does not survive contact with GM. **The inputs carry no `data-automation-id` at
all.** It sits on a wrapper three levels up, and under a different naming scheme:

| adapter's `ID_MAP` expects | GM's wrapper actually has | GM's input `name` |
|---|---|---|
| `legalNameSection_firstName` | `formField-legalName--firstName` | `legalName--firstName` |
| `legalNameSection_lastName` | `formField-legalName--lastName` | `legalName--lastName` |
| `addressSection_addressLine1` | `formField-addressLine1` | `addressLine1` |
| `addressSection_city` | `formField-city` | `city` |
| `addressSection_postalCode` | `formField-postalCode` | `postalCode` |
| `phoneNumber` | `formField-phoneNumber` | `phoneNumber` |

Not one entry matches. The adapter's first pass fills **nothing** on this tenant;
everything that works is the label-matching fallback. The input `name` is the
clean, stable key here (`addressLine1`, `city`, `postalCode`, `phoneNumber`) —
that, or the `formField-*` id on the ancestor, is what the adapter should read.

### The honeypot — the reason this survey was worth doing

Step 1 ships a bot trap — on **all three** tenants sampled, so treat it as
standard Workday rather than one employer's idea:

```
name="website"  data-automation-id="beecatcher"  1×1 px
label: "Enter website. This input is for robots only, do not enter if you're human."
```

Mastercard's is 1 × **0.01** px. It is `display:block`, `visibility:visible`,
`opacity:1`, with a live `offsetParent` — every ordinary hidden-field check
misses it. And `/\bwebsite\b/`
matched it, so autofill would have posted a portfolio URL into a trap whose only
purpose is to identify you as a bot.

Guarded two ways in `field-matcher.js`: `isHoneypot()` (1×1 or smaller, parked
off-canvas, or a trap-shaped name) and `looksLikeTrapText()`, which makes a label
that announces itself as a trap match nothing at all.

## Keeping this honest

`tests/test-field-matcher.js` runs all 67 surveyed labels — including the
honeypot — through the matcher, and again through the rules lifted out of
`ios/Recon/AutofillWebView.swift`, so the two clients cannot drift.
