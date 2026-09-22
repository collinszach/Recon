"""Metro classifier — tags a role's free-text location with one of Zach's
target metros so the pipeline can surface and filter by geography.

ATS location strings are messy ("New York, NY", "NYC / Remote", "Mount
Pleasant, South Carolina, United States", "Greater Boston Area"). We map them
to a small set of target metro slugs. Disambiguation matters: Charleston SC vs
WV, Cambridge MA vs UK, Washington DC vs WA state — so ambiguous city names
require a corroborating state hint.

Pure stdlib so it runs in the worker or a unit test without the app.
"""
import re

# Target metros, in match priority order. Each entry: (slug, label, pattern).
# Patterns run against a lowercased, whitespace-normalized location string.
# `remote` is matched separately (a role can be "Remote - US" with no city).
_METROS: list[tuple[str, str, re.Pattern]] = [
    ("charleston", "Charleston, SC", re.compile(
        r"\b(charleston|mount\s+pleasant|north\s+charleston|summerville|daniel\s+island)\b"
        r"(?=.*\b(sc|south\s+carolina)\b)"   # require SC to exclude Charleston WV
        r"|\bcharleston\s*,?\s*sc\b",
        re.IGNORECASE)),

    ("nyc", "New York City", re.compile(
        r"\b(new\s+york\s+city|nyc|manhattan|brooklyn|\bqueens\b|the\s+bronx|"
        r"long\s+island\s+city|jersey\s+city|hoboken)\b"
        r"|\bnew\s+york\s*,?\s*(ny|new\s+york)\b"
        r"|\bnew\s+york\b(?=.*\bny\b)",
        re.IGNORECASE)),

    ("dc_metro", "DC / NoVA / MD", re.compile(
        r"\b(washington\s*,?\s*d\.?c\.?|washington\s+dc|"
        r"arlington|alexandria|reston|tysons|mclean|herndon|fairfax|falls\s+church|"
        r"crystal\s+city|bethesda|rockville|silver\s+spring|gaithersburg|college\s+park)\b"
        r"|\bwashington\b(?=.*\b(dc|d\.c\.)\b)",
        re.IGNORECASE)),

    ("socal", "Southern California", re.compile(
        r"\b(los\s+angeles|\bl\.?a\.?\b|irvine|orange\s+county|san\s+diego|"
        r"santa\s+monica|pasadena|long\s+beach|anaheim|costa\s+mesa|el\s+segundo|"
        r"culver\s+city|carlsbad|torrance|burbank|newport\s+beach|san\s+pedro)\b",
        re.IGNORECASE)),

    ("boston", "Greater Boston", re.compile(
        r"\b(boston|somerville|waltham|newton|burlington\s*,?\s*ma|medford\s*,?\s*ma|"
        r"greater\s+boston)\b"
        r"|\bcambridge\b(?=.*\b(ma|mass|massachusetts)\b)"
        r"|\bcambridge\s*,?\s*ma\b",
        re.IGNORECASE)),

    ("pennsylvania", "Pennsylvania", re.compile(
        r"\b(philadelphia|philly|pittsburgh)\b"
        r"|\b(pa|pennsylvania)\b(?=.*\b(philadelphia|philly|pittsburgh|king\s+of\s+prussia|malvern)\b)"
        r"|\b(king\s+of\s+prussia|malvern|conshohocken)\b",
        re.IGNORECASE)),

    ("rtp", "Raleigh-Durham / RTP", re.compile(
        r"\b(raleigh|durham|chapel\s+hill|\bcary\b|research\s+triangle|\brtp\b)\b",
        re.IGNORECASE)),

    ("bay_area", "SF Bay Area", re.compile(
        r"\b(san\s+francisco|\bsf\b|oakland|berkeley|san\s+jose|silicon\s+valley|"
        r"palo\s+alto|mountain\s+view|redwood\s+city|menlo\s+park|sunnyvale|"
        r"santa\s+clara|cupertino|fremont|south\s+bay|peninsula)\b",
        re.IGNORECASE)),
]

_REMOTE_RE = re.compile(
    r"\bremote\b|\bwork\s+from\s+home\b|\bwfh\b|\bdistributed\b|\banywhere\b",
    re.IGNORECASE)
# Remote that is clearly NOT US-eligible — don't tag those as our remote bucket.
_REMOTE_NON_US_RE = re.compile(
    r"\bremote\b.*\b(emea|apac|europe|uk|united\s+kingdom|india|canada\s+only|"
    r"germany|ireland|australia|latam)\b|"
    r"\b(emea|apac|europe|uk|india|germany|ireland|australia|latam)\b.*\bremote\b",
    re.IGNORECASE)

# Public list of (slug, label) for API/clients to render the facet.
METROS: list[tuple[str, str]] = [(s, l) for s, l, _ in _METROS] + [("remote", "Remote (US)")]
METRO_SLUGS: set[str] = {s for s, _ in METROS}


# ─── Broad US-state classifier ──────────────────────────────────────────────
# The 9-metro list above is deliberately narrow (Zach's specific relocation
# targets, used as a positive scoring signal). It will always miss somewhere
# he hasn't thought of yet (2026-08-16: "Denver/CO and other areas I might not
# be considering") — so for BROWSING/FILTERING, tag every role with its US
# state instead. 50 states + DC is exhaustive by construction; no ongoing
# hand-curation needed, unlike a city list.
US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
# Match "City, ST" / "City, ST, USA" — abbreviation directly after a comma is
# the reliable ATS pattern (raw word-boundary matching on "OR"/"IN"/"HI"/"ME"
# etc. would false-positive constantly without it).
_STATE_ABBR_RE = re.compile(r",\s*(" + "|".join(US_STATES) + r")\b(?!\.\w)")
# Fallback: full state name anywhere in the string.
_STATE_NAME_RE = {
    code: re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
    for code, name in US_STATES.items()
}
_INTERNATIONAL_HINT_RE = re.compile(
    r"\b(india|uk|united\s+kingdom|london|canada|toronto|vancouver|montreal|germany|berlin|munich|"
    r"amsterdam|netherlands|ireland|dublin|australia|sydney|melbourne|singapore|japan|tokyo|"
    r"china|beijing|shanghai|hong\s+kong|france|paris|spain|madrid|barcelona|italy|milan|rome|"
    r"switzerland|zurich|geneva|austria|vienna|belgium|brussels|sweden|stockholm|denmark|copenhagen|"
    r"norway|oslo|finland|helsinki|poland|warsaw|portugal|lisbon|israel|tel\s+aviv|"
    r"united\s+arab\s+emirates|\buae\b|dubai|abu\s+dhabi|south\s+korea|seoul|taiwan|taipei|"
    r"vietnam|philippines|indonesia|thailand|malaysia|new\s+zealand|"
    r"mexico(?!\s*,?\s*missouri)|brazil|argentina|colombia(?!\s*,?\s*(sc|south\s+carolina))|"
    # Added 2026-09-21 after US-only filtering: the list above missed whole
    # regions, so "Istanbul, Turkey", "Bucharest, Romania" and "Libreville
    # Gabon" came back unresolved and sat in a US-only feed. Country names
    # only, plus cities that can't be confused with a US one — no "Athens"
    # (GA), "Lima" (OH), "Birmingham" (AL) or "Cambridge" (MA).
    r"frankfurt|hamburg|stuttgart|cologne|d\u00fcsseldorf|dusseldorf|"
    r"lyon|toulouse|marseille|rotterdam|utrecht|antwerp|ghent|basel|bern|"
    r"turkey|t\u00fcrkiye|istanbul|romania|bucharest|bulgaria|hungary|budapest|"
    r"czech(ia|\s+republic)?|prague|slovakia|bratislava|slovenia|ljubljana|croatia|zagreb|"
    r"serbia|belgrade|ukraine|kyiv|kiev|estonia|tallinn|latvia|\briga\b|lithuania|vilnius|"
    r"iceland|reykjavik|luxembourg|\bmalta\b|cyprus|greece(?!\s*,?\s*(ny|new\s+york))|"
    r"gabon|nigeria|lagos|kenya|nairobi|south\s+africa|johannesburg|cape\s+town|"
    r"egypt|cairo|morocco|casablanca|tunisia|ghana|accra|ethiopia|"
    r"saudi\s+arabia|riyadh|jeddah|qatar|doha|kuwait|bahrain|\boman\b|jordan(?=\s*,)|"
    r"pakistan|karachi|lahore|bangladesh|dhaka|sri\s+lanka|colombo|nepal|kathmandu|"
    r"bengaluru|bangalore|hyderabad(?!\s*,?\s*(al|alabama))|\bpune\b|chennai|mumbai|"
    r"gurugram|gurgaon|noida|kolkata|ahmedabad|\bdelhi\b|"
    r"auckland|wellington(?=\s*,?\s*(nz|new\s+zealand))|christchurch|"
    r"peru(?!\s*,?\s*(in|indiana|il|illinois))|chile|uruguay|montevideo|ecuador|quito|"
    r"\bpanama\b|costa\s+rica|guatemala|el\s+salvador|honduras|bolivia|paraguay|"
    r"kazakhstan|uzbekistan|azerbaijan|armenia|\brussia\b|moscow|"
    r"emea|apac|latam)\b", re.IGNORECASE)
# Adzuna renders US towns as "City, Some County" — no state, no country. The
# county suffix is itself the US signal, and without it these looked exactly
# like the unresolved foreign strings above ("Lincoln, Lancaster County" vs
# "Bucharest, Romania").
_US_COUNTY_RE = re.compile(r",\s*[A-Za-z .'\-]+\s+(County|Parish|Borough)\b", re.IGNORECASE)
# Explicit US marker — when present alongside an international hint (a genuine
# multi-region posting that also happens to say "EMEA"), don't let the hint
# override real US state matches.
_US_MARKER_RE = re.compile(r"\b(united\s+states|u\.s\.a?\.?)\b", re.IGNORECASE)
# Amazon/Workday-style prefixed codes: "US-CA-Menlo Park", "US_WA_Bellevue".
_US_PREFIX_RE = re.compile(r"\bUS[-_](" + "|".join(US_STATES) + r")\b")
# Bare city names, the single biggest gap (2026-09-21: 5,170 of 24,757 open
# roles had no state, and "San Francisco" alone — no state, no country — was
# 1,023 of them; Adzuna's "City, County" form, e.g. "Pittsburgh, Allegheny
# County", defeats the comma-abbreviation pattern the same way).
#
# Deliberately limited to cities whose name is unambiguous in a US job posting.
# Ambiguous ones are left out rather than guessed: Portland (OR/ME), Columbus
# (OH/GA), Springfield, Kansas City (MO/KS), Charleston (SC/WV), Rochester
# (NY/MN), Aurora (CO/IL) — those still fall through to [] unless the string
# names the state itself.
_CITY_STATE: dict[str, str] = {
    # Bay Area
    "san francisco": "CA", "south san francisco": "CA", "san jose": "CA",
    "sunnyvale": "CA", "santa clara": "CA", "mountain view": "CA", "palo alto": "CA",
    "menlo park": "CA", "cupertino": "CA", "redwood city": "CA", "foster city": "CA",
    "san mateo": "CA", "fremont": "CA", "oakland": "CA", "berkeley": "CA",
    "emeryville": "CA", "milpitas": "CA", "campbell": "CA", "burlingame": "CA",
    "pleasanton": "CA", "walnut creek": "CA", "san ramon": "CA", "livermore": "CA",
    # SoCal + rest of CA
    "los angeles": "CA", "santa monica": "CA", "culver city": "CA", "pasadena": "CA",
    "el segundo": "CA", "long beach": "CA", "irvine": "CA", "costa mesa": "CA",
    "san diego": "CA", "carlsbad": "CA", "anaheim": "CA", "torrance": "CA",
    "burbank": "CA", "glendale": "CA", "sacramento": "CA", "hawthorne": "CA",
    # Pacific NW
    "seattle": "WA", "bellevue": "WA", "redmond": "WA", "kirkland": "WA",
    "tacoma": "WA", "spokane": "WA", "everett": "WA", "renton": "WA",
    "beaverton": "OR", "hillsboro": "OR",
    # NYC + NE
    "new york": "NY", "new york city": "NY", "brooklyn": "NY", "manhattan": "NY",
    "queens": "NY", "bronx": "NY", "long island city": "NY", "albany": "NY",
    "buffalo": "NY", "syracuse": "NY", "yonkers": "NY", "white plains": "NY",
    "boston": "MA", "cambridge": "MA", "somerville": "MA", "waltham": "MA",
    "burlington": "MA", "lexington": "MA", "needham": "MA", "quincy": "MA",
    "newton": "MA", "andover": "MA", "worcester": "MA",
    # No "springfield": MO and IL are both larger than the MA one, and the
    # comment above promises ambiguous cities are left unresolved. The table
    # said otherwise until a test caught the contradiction.
    "providence": "RI", "hartford": "CT", "stamford": "CT", "new haven": "CT",
    "greenwich": "CT", "jersey city": "NJ", "hoboken": "NJ", "newark": "NJ",
    "princeton": "NJ", "philadelphia": "PA", "pittsburgh": "PA",
    # DC area
    "washington": "DC", "arlington": "VA", "alexandria": "VA", "reston": "VA",
    "mclean": "VA", "herndon": "VA", "tysons": "VA", "chantilly": "VA",
    "richmond": "VA", "bethesda": "MD", "rockville": "MD", "baltimore": "MD",
    "annapolis": "MD", "college park": "MD", "silver spring": "MD",
    # South + Texas
    "atlanta": "GA", "alpharetta": "GA", "savannah": "GA", "charlotte": "NC",
    "raleigh": "NC", "durham": "NC", "cary": "NC", "greensboro": "NC",
    "nashville": "TN", "memphis": "TN", "knoxville": "TN", "chattanooga": "TN",
    "miami": "FL", "orlando": "FL", "tampa": "FL", "jacksonville": "FL",
    "fort lauderdale": "FL", "boca raton": "FL", "st. petersburg": "FL",
    "austin": "TX", "dallas": "TX", "houston": "TX", "san antonio": "TX",
    "plano": "TX", "irving": "TX", "fort worth": "TX", "richardson": "TX",
    "el paso": "TX", "round rock": "TX", "new orleans": "LA", "birmingham": "AL",
    "huntsville": "AL", "louisville": "KY", "little rock": "AR",
    # Midwest + Mountain
    "chicago": "IL", "evanston": "IL", "naperville": "IL", "schaumburg": "IL",
    "detroit": "MI", "ann arbor": "MI", "dearborn": "MI", "grand rapids": "MI",
    "minneapolis": "MN", "st. paul": "MN", "bloomington": "MN", "rochester": "MN",
    "milwaukee": "WI", "madison": "WI", "indianapolis": "IN", "cleveland": "OH",
    "cincinnati": "OH", "dublin": "OH", "st. louis": "MO", "des moines": "IA",
    "omaha": "NE", "denver": "CO", "boulder": "CO", "colorado springs": "CO",
    "salt lake city": "UT", "provo": "UT", "lehi": "UT", "phoenix": "AZ",
    "tempe": "AZ", "scottsdale": "AZ", "chandler": "AZ", "tucson": "AZ",
    "las vegas": "NV", "reno": "NV", "boise": "ID", "albuquerque": "NM",
}
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in
                      sorted(_CITY_STATE, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)


def states_of(location: str | None) -> list[str]:
    """Resolve each segment of a multi-location posting independently, then
    union the results in order.

    Segment-wise matters for the international guard: "Atlanta, GA; London, UK"
    is a real US role with a second office, but evaluating the whole string at
    once let the "UK" hint short-circuit the entire posting to international —
    so a US-only feed would hide it. Splitting also keeps the case the guard
    exists for: "Amsterdam, NH" is one segment, hint and abbreviation together,
    and still resolves to international (Lucid's Netherlands office, 2026-08-16).
    """
    if not location:
        return []
    parts = [p for p in re.split(r"[;|\n]+", location) if p.strip()]
    if len(parts) < 2:
        return _states_of_one(location)
    found: list[str] = []
    for part in parts:
        for code in _states_of_one(part):
            if code not in found:
                found.append(code)
    # A posting with a US leg is a US posting; keep "international" alongside so
    # the facet still shows the other offices.
    return found


def _states_of_one(location: str | None) -> list[str]:
    """ALL US state codes present in a location string, in first-occurrence
    order, or ['remote'] / ['international'] / [] (unparseable).

    Multi-location postings are common ("Atlanta, GA; Denver, CO; LA, CA" or
    "Atlanta, Georgia, ... Los Angeles, California, ..."), and returning only
    one state silently drops the others from every state-scoped filter — a
    role open in Denver AND LA would only ever show up under whichever state
    happened to be checked first. Confirmed 2026-08-16: a single-value
    fallback that checked full state names in a fixed dict order (CA before
    CO, GA, ...) was mis-tagging Colorado (and other alphabetically-later
    states) as California whenever both names appeared in the same multi-city
    posting — which is also why Colorado internships weren't showing up.
    """
    if not location:
        return []
    hay = re.sub(r"\s+", " ", location).strip()
    # A named foreign city/country wins over a coincidental state-abbreviation
    # match — confirmed 2026-08-16: Lucid Motors' Greenhouse board lists their
    # Netherlands office as literally "Amsterdam, NH", which the abbreviation
    # regex below happily (wrongly) parsed as New Hampshire. Skip straight to
    # international UNLESS the string also explicitly says "United States"
    # (a genuine multi-region posting that happens to mention "EMEA" too).
    if _INTERNATIONAL_HINT_RE.search(hay) and not _US_MARKER_RE.search(hay):
        return ["international"]
    found: list[str] = []
    for m in _STATE_ABBR_RE.finditer(hay):
        code = m.group(1).upper()
        if code not in found:
            found.append(code)
    # Full-name fallback, ordered by position in the string (not dict order),
    # so multi-location postings resolve every state mentioned, not just
    # whichever one happens to sort first in US_STATES.
    name_hits: list[tuple[int, str]] = []
    for code, pat in _STATE_NAME_RE.items():
        m = pat.search(hay)
        if m:
            name_hits.append((m.start(), code))
    for _, code in sorted(name_hits):
        if code not in found:
            found.append(code)
    # "US-CA-Menlo Park" — a prefixed code, not a comma pattern.
    for m in _US_PREFIX_RE.finditer(hay):
        code = m.group(1).upper()
        if code not in found:
            found.append(code)
    # Bare city names ("San Francisco", "Sunnyvale") and Adzuna's "City, County"
    # form, in order of appearance so multi-city postings resolve every state.
    if not found:
        for m in _CITY_RE.finditer(hay):
            code = _CITY_STATE[m.group(1).lower()]
            if code not in found:
                found.append(code)
    if found:
        return found
    if _REMOTE_RE.search(hay) and not _REMOTE_NON_US_RE.search(hay):
        return ["remote"]
    if _INTERNATIONAL_HINT_RE.search(hay):
        return ["international"]
    return []


def state_of(location: str | None) -> str | None:
    """Back-compat single-value accessor (first match) — prefer states_of()."""
    found = states_of(location)
    return found[0] if found else None


def states_csv(location: str | None) -> str | None:
    """Comma-joined states_of(), for storing in Role.state (a single TEXT
    column holding possibly-multiple codes — see states_of() docstring)."""
    found = states_of(location)
    return ",".join(found) if found else None


STATE_LABELS: list[tuple[str, str]] = (
    sorted(US_STATES.items(), key=lambda kv: kv[1])
    + [("remote", "Remote (US)"), ("international", "International")]
)


def metro_of(location: str | None) -> str | None:
    """Return the target-metro slug for a location string, or None.

    A specific target city wins over a generic remote tag (a "Remote / NYC"
    posting is tagged nyc). Pure US-remote with no city -> 'remote'.
    """
    if not location:
        return None
    hay = re.sub(r"\s+", " ", location).strip()
    for slug, _label, pat in _METROS:
        if pat.search(hay):
            return slug
    if _REMOTE_RE.search(hay) and not _REMOTE_NON_US_RE.search(hay):
        return "remote"
    return None


def is_us(location: str | None, state: str | None = None,
          title: str | None = None) -> bool:
    """Is this role in the US (or US-remote)?

    `state` is the stored comma-joined result of states_of(); pass it to avoid
    re-parsing. Unresolvable locations ("3 Locations", "TAURUS") count as US —
    a US-only feed should fail toward showing you something rather than hiding
    a real posting on a string nobody can parse.
    """
    codes = {c for c in (state or "").split(",") if c}
    if codes & set(US_STATES) or "remote" in codes:
        return True          # a multi-region posting with a US leg still counts
    if "international" in codes:
        return False
    # Some boards give no location at all — Accenture's Workday returns NULL —
    # and then the country is only in the title: "Internship – Technology
    # Strategy & Transformation Luxembourg" was sitting in a US-only feed.
    if not location:
        if title and _INTERNATIONAL_HINT_RE.search(title) and not _US_MARKER_RE.search(title):
            return False
        return True
    if _US_COUNTY_RE.search(location):
        return True
    if _INTERNATIONAL_HINT_RE.search(location) and not _US_MARKER_RE.search(location):
        return False
    # A location that parses as nothing useful ("TAURUS") leaves the title as
    # the only remaining signal.
    if title and _INTERNATIONAL_HINT_RE.search(title) and not _US_MARKER_RE.search(title):
        return False
    return True
