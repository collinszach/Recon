"""Read a PitchBook company export (CSV) into startup records.

Pure stdlib so CI can test it. PitchBook's column names vary a little by
export template and version ("Companies" vs "Company Name", "Last Financing
Size" vs "Last Financing Size (USD M)"), so columns are matched by what they
mean, not by exact header text.

PitchBook chooses which startups to watch; Recon does the rest — finding each
one's job board, checking the board is really theirs (scan/identity.py), and
pulling its roles. Only data Zach exported himself is read: no scraping, no
login automation.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

# meaning -> header patterns (lowercased, punctuation-insensitive)
_COLUMNS = {
    "name":        [r"^compan(y|ies)( name)?$", r"^name$"],
    "website":     [r"^website", r"^url$", r"domain"],
    "description": [r"^description", r"^business description", r"one.?liner"],
    "hq":          [r"^hq location", r"^headquarters", r"^hq$", r"^location$"],
    "industry":    [r"primary industry (sector|group|code)", r"^industry", r"vertical"],
    "verticals":   [r"^verticals?$", r"^all industries"],
    "round_date":  [r"last financing date", r"last (deal|round) date"],
    "round_type":  [r"last financing (deal )?type$", r"last (deal|round) type", r"^stage$",
                    r"company financing status"],
    "round_size":  [r"last financing size", r"last (deal|round) size"],
    "total":       [r"total raised", r"total funding"],
    "employees":   [r"^employees", r"headcount", r"^employee count"],
    "founded":     [r"year founded", r"^founded"],
}

# Recon's startup sectors, by keywords in PitchBook's industry/vertical text.
_SECTORS = [
    ("defense", r"defen[cs]e|aerospace|national security|military|space tech|government"),
    ("sustainability_energy", r"climate|clean ?tech|energy|battery|storage|solar|wind|hydrogen|"
                              r"carbon|nuclear|fusion|geothermal|mobility tech|ev\b|electric vehicle"),
    ("fintech", r"fin ?tech|financial|payments?|banking|lending|insur|crypto|blockchain|"
                r"capital markets|wealth|accounting"),
    ("product_tech_data", r"software|saas|artificial intelligence|\bai\b|machine learning|"
                          r"data|analytics|developer|infrastructure|cloud|robotics|enterprise"),
]


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (h or "").lower())).strip()


def map_columns(headers: list[str]) -> dict[str, str]:
    """{meaning: actual header} for the headers this export has."""
    out: dict[str, str] = {}
    for meaning, pats in _COLUMNS.items():
        for h in headers:
            if any(re.search(p, _norm(h)) for p in pats):
                out.setdefault(meaning, h)
                break
    return out


def _money_m(v: str | None) -> float | None:
    """'$12.50' / '12.5' / '1,200.00' (USD millions in PitchBook exports) -> 12.5."""
    if not v:
        return None
    s = re.sub(r"[^\d.]", "", v)
    try:
        return round(float(s), 2) if s else None
    except ValueError:
        return None


def _int(v: str | None) -> int | None:
    s = re.sub(r"[^\d]", "", v or "")
    return int(s) if s else None


def _date(v: str | None) -> date | None:
    v = (v or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _website(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v or " " in v or "." not in v:
        return None
    return v if v.startswith("http") else f"https://{v}"


def sector_of(*texts: str | None) -> str:
    hay = " ".join(t for t in texts if t).lower()
    for sector, pat in _SECTORS:
        if re.search(pat, hay):
            return sector
    return "other"


def parse(text: str) -> tuple[list[dict], dict[str, str]]:
    """(records, column map). Skips PitchBook's title/notes rows above the
    header by finding the first row that has a company-name column."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    start = next((i for i, r in enumerate(rows) if "name" in map_columns(r)), None)
    if start is None:
        return [], {}
    headers = rows[start]
    cols = map_columns(headers)
    idx = {m: headers.index(h) for m, h in cols.items()}
    out = []
    for r in rows[start + 1:]:
        get = lambda m: (r[idx[m]].strip() if m in idx and idx[m] < len(r) else "")  # noqa: E731
        name = get("name")
        if not name or name.lower().startswith(("total", "source:", "data provided")):
            continue
        out.append({
            "name": name[:200],
            "website": _website(get("website")),
            "one_liner": get("description")[:600] or None,
            "hq_location": get("hq") or None,
            "sector": sector_of(get("industry"), get("verticals"), get("description")),
            "last_round_date": _date(get("round_date")),
            "last_round_type": get("round_type") or None,
            "last_round_m": _money_m(get("round_size")),
            "total_raised_m": _money_m(get("total")),
            "headcount": _int(get("employees")),
            "founded_year": _int(get("founded")),
        })
    return out, cols
