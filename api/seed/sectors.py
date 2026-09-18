"""Rule-based company sector classifier — keyword/name matching, zero AI cost.

Used to tag Company.sector so internships can be filtered by sector (e.g. "big
tech") the same way they're filtered by MBA-track. Best-effort: unmatched
companies stay sector=None ("other" in the API), refined over time by adding
names/keywords here rather than hand-editing every company row.
"""
import re

# Recognizable mega-cap tech employers — the "big tech" bucket specifically
# (distinct from "startup" or plain "enterprise" software).
_BIG_TECH = {
    "google", "alphabet", "meta", "facebook", "amazon", "apple", "microsoft",
    "nvidia", "netflix", "salesforce", "oracle", "adobe", "sap", "ibm", "cisco",
    "intel", "qualcomm", "linkedin", "uber", "airbnb", "spotify", "paypal",
    "servicenow", "workday", "vmware", "dell", "hp", "hewlett packard",
    "palo alto networks", "crowdstrike", "okta", "atlassian", "snowflake",
    "twilio", "block", "square", "shopify", "doordash", "pinterest", "snap",
    "x corp", "twitter", "tiktok", "bytedance",
}

_FINANCE = {
    "capital one", "jpmorgan", "jp morgan", "goldman sachs", "morgan stanley",
    "citi", "citigroup", "bank of america", "wells fargo", "visa", "mastercard",
    "american express", "amex", "fidelity", "charles schwab", "blackrock",
    "stripe", "plaid", "robinhood", "coinbase", "affirm", "chime", "sofi",
    "betterment", "brex", "ramp", "mercury",
}

_DEFENSE_AEROSPACE = {
    "anduril", "spacex", "palantir", "lockheed", "raytheon", "rtx",
    "northrop grumman", "general dynamics", "l3harris", "boeing",
    "collins aerospace", "textron", "leidos", "booz allen", "saildrone",
    "shield ai", "hermeus", "relativity space", "rocket lab", "firefly",
    "epirus", "castelion", "applied intuition",
}

_CONSULTING = {
    "mckinsey", "bain", "bcg", "boston consulting", "deloitte", "accenture",
    "pwc", "kpmg", "ey ", "ernst & young",
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").lower()).strip()


def sector_for(company_name: str) -> str | None:
    """Best-effort sector tag for a company name. None means unclassified."""
    n = _norm(company_name)
    if not n:
        return None
    for bucket, names in (
        ("big_tech", _BIG_TECH),
        ("finance", _FINANCE),
        ("defense_aerospace", _DEFENSE_AEROSPACE),
        ("consulting", _CONSULTING),
    ):
        if any(name in n or n in name for name in names):
            return bucket
    return None
