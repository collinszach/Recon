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
