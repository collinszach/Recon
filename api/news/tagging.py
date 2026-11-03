"""What an article is about, and whether it is about the company at all.

Pure stdlib, no DB, no network — so api/tests/test_logic.py can hold it to the
cases that matter. Keyword rules, not an LLM: headlines are short and formulaic
("X raises $40M Series B", "X lays off 10% of staff"), rules get those right,
and it keeps the news feature at zero AI cost.
"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Most job-hunt-relevant first: the brief picks each company's top article by
# this order, and the app shows tags in it.
TAG_ORDER = ["layoffs", "hiring_freeze", "funding", "acquisition", "leadership",
             "hiring", "launch", "earnings"]

# Tags worth a line in the daily brief. Launches and earnings are kept on the
# company page but are too routine to interrupt the morning with.
BRIEF_TAGS = {"layoffs", "hiring_freeze", "funding", "acquisition", "leadership", "hiring"}

_RULES: dict[str, re.Pattern] = {
    "layoffs": re.compile(
        r"\blay(s|ing)? ?offs?\b|\blaid off\b|\bjob cuts?\b|\bcuts? (\d[\d,]*|hundreds of|thousands of) "
        r"(jobs|roles|employees|workers|staff)\b|\bcut(s|ting)? \d+% of\b|\bworkforce reduction\b|"
        r"\breduc(e|es|ing) (its )?(headcount|workforce)\b|\brestructur(e|es|ing)\b|\bdownsiz"),
    "hiring_freeze": re.compile(
        r"\bhiring freeze\b|\bfreez(e|es|ing) (on )?hiring\b|\bpaus(e|es|ed|ing) (on )?hiring\b|"
        r"\bslow(s|ed|ing)? (down )?hiring\b|\bhalt(s|ed|ing)? hiring\b"),
    "funding": re.compile(
        r"\brais(e|es|ed|ing) \$|\bseries [a-h]\b|\bseed (round|funding)\b|\bfunding round\b|"
        r"\bvaluation\b|\bvalued at\b|\bventure (funding|round)\b|\b(files|filing) (for|to go) (an )?ipo\b|"
        r"\bipo\b|\bgoes public\b|\bsecures \$"),
    "acquisition": re.compile(
        r"\bacquir(e|es|ed|ing)\b|\bacquisition\b|\bto buy\b|\bbuys\b|\bmerg(e|er|es|ing)\b|\btakeover\b"),
    "leadership": re.compile(
        r"\b(names|appoints|hires|taps|promotes) .{0,40}\b(ceo|cfo|cto|coo|cpo|president|chief|head of)\b|"
        r"\b(ceo|cfo|cto|coo|founder|president|chief executive)\b.{0,30}\b(steps? down|resign(s|ed)?|"
        r"depart(s|ing)?|exit(s|ing)?|leav(es|ing)|ousted|fired|retir(e|es|ing))\b|\bnew (ceo|cfo|cto|coo)\b|"
        r"\bsucceed(s)? .{0,30}\bas (ceo|chief)\b"),
    "hiring": re.compile(
        r"\b(plans|plan|looks|aims) to hire\b|\bhiring spree\b|\bto hire \d|\badd(s|ing)? [\d,]+ (jobs|roles|employees)\b|"
        r"\bnew (office|headquarters|hq|hub)\b|\bopens? .{0,30}\b(office|hub|headquarters|facility|factory)\b|"
        r"\bexpan(ds|sion) (to|into|in)\b|\bnew jobs\b"),
    "launch": re.compile(
        # verb forms only: "launch" the noun ("the launch company", "launch
        # window") is everywhere in space-industry coverage
        r"\blaunch(es|ed|ing)\b|\bto launch\b|\bunveil(s|ed|ing)?\b|\bdebut(s|ed)?\b|\brolls? out\b|\bintroduc(es|ed|ing)\b|"
        r"\bannounc(es|ed) (new|the)\b|\breleas(es|ed) (new|its)\b"),
    "earnings": re.compile(
        r"\bearnings\b|\bquarterly (results|revenue)\b|\bq[1-4] (results|revenue|earnings)\b|"
        r"\b(fiscal|full)[- ]year (results|guidance)\b|\bguidance\b|\brevenue (rose|fell|grew|jumps|drops)\b"),
}


def tag(title: str, description: str | None = None) -> list[str]:
    text = f"{title} {description or ''}".lower()
    found = {t for t, rx in _RULES.items() if rx.search(text)}
    # "slows hiring" also reads as a hiring story; the freeze is the news.
    if "hiring_freeze" in found:
        found.discard("hiring")
    return [t for t in TAG_ORDER if t in found]


# ── which phrases identify a company ───────────────────────────────────────
# A bare name is the query AND the match test by default. These are the names
# that are also ordinary words or other things ("Target", "Figure", "Block",
# "Chase"); each gets phrases specific enough to mean the company. An empty
# list means "too generic to search for" — the company is skipped.
PHRASE_OVERRIDES: dict[str, list[str]] = {
    "Target": ["Target Corp", "Target Corporation", "retailer Target"],
    "Future": [],
    "Superpower": [],
    "Levels": ["Levels Health"],
    "Via": ["Via Transportation"],
    "Vast": ["Vast Space", "Vast Haven"],
    "Figure": ["Figure AI"],
    "Block": ["Block Inc", "Jack Dorsey's Block"],
    "Aurora": ["Aurora Innovation"],
    "Sierra": ["Sierra AI", "Bret Taylor's Sierra"],
    "Writer": ["Writer AI", "Writer Inc"],
    "Modal": ["Modal Labs"],
    "Primer": ["Primer AI", "Primer Technologies"],
    "Chase": ["Chase Bank", "JPMorgan Chase"],
    "Discover": ["Discover Financial"],
    "Mercury": ["Mercury Technologies", "fintech Mercury", "Mercury bank"],
    "Motive": ["Motive Technologies"],
    "Alloy": ["Alloy Labs", "fintech Alloy"],
    "Toast": ["Toast Inc", "Toast restaurant"],
    "Elastic": ["Elastic N.V.", "Elastic NV", "Elasticsearch"],
    "Glean": ["Glean AI", "Glean Technologies"],
    "Notion": ["Notion Labs"],
    "Ramp": ["Ramp fintech", "fintech Ramp"],
    "Plaid": ["Plaid Inc", "fintech Plaid"],
    "Chime": ["Chime Financial"],
    "Apptronik": ["Apptronik"],
    "Meta Reality Labs": ["Reality Labs"],
    "Raytheon Technologies (RTX)": ["Raytheon", "RTX Corp"],
    "McKinsey & Company": ["McKinsey"],
    "Boston Consulting Group": ["Boston Consulting Group", "BCG"],
    "The Walt Disney Company": ["Disney"],
    "The Coca-Cola Company": ["Coca-Cola"],
    "Ford Motor Company": ["Ford Motor"],
    "UnitedHealth Group": ["UnitedHealth"],
    "Costco Wholesale": ["Costco"],
    "The Home Depot": ["Home Depot"],
    "JPMorgan Chase": ["JPMorgan"],
    "Lucid Motors": ["Lucid Motors", "Lucid Group"],
    "Progressive Insurance": ["Progressive Insurance", "Progressive Corp"],
    "Incode Technologies": ["Incode"],
}

_SUFFIX = re.compile(r",?\s+(inc\.?|corp\.?|corporation|llc|ltd\.?|co\.?|company)$", re.I)


def phrases_for(name: str) -> list[str]:
    if name in PHRASE_OVERRIDES:
        return PHRASE_OVERRIDES[name]
    clean = re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    clean = re.sub(r"^the\s+", "", clean, flags=re.I)
    clean = _SUFFIX.sub("", clean).strip()
    return [clean] if len(clean) >= 2 else []


def mentions(phrases: list[str], title: str, description: str | None = None) -> bool:
    """True when the article names the company. Case-sensitive on purpose:
    "Apple" the company is capitalised, "apple pie" is not. Providers search
    loosely (GDELT matches page bodies), so this is what keeps a story that
    merely links to the company out of its feed."""
    text = f"{title} {description or ''}".replace("’", "'")
    return any(re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", text) for p in phrases)


# ── dedupe keys ────────────────────────────────────────────────────────────
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|cmpid$|ocid$|guccounter$)", re.I)


def url_key(url: str) -> str:
    """Scheme-less, www-less, tracking-param-free, trailing-slash-free URL."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    return urlunsplit(("", host, parts.path.rstrip("/"), query, "")).lstrip("/")[:500]


def title_key(title: str) -> str:
    """Headline with the outlet suffix and punctuation stripped — the same wire
    story syndicated as "X raises $40M - Reuters" and "X raises $40M | Yahoo"
    collapses to one key."""
    t = re.split(r"\s+[-|–—]\s+(?=[^-|–—]{2,40}$)", title.strip())[0]
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()[:300]
