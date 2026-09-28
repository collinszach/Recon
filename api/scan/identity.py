"""Is this job board actually *this* company's?

Pure stdlib on purpose, so the judgment can be tested in CI without installing
anything, and kept apart from the network code that gathers the evidence.

Why it exists: `ats_discovery.probe()` accepts a board if it answers with at
least one posting. That proves a board exists, not whose it is. On 2026-09-28,
five of fifteen hand-picked slugs answered with live postings from a different
company that owned the same word:

    wise      -> "Wise Worksite Field Sales", an insurance sales org
    axiom     -> Axiom Law (axiomlaw.com), not Axiom Space
    neon      -> Neon the Brazilian bank, not Neon the Postgres company
    watershed -> Watershed Informatics, not the carbon-accounting company
    arcadia   -> a life-sciences data business, not the energy company

Promoting a tracked startup onto a board like that pours someone else's jobs
into the feed under your company's name, silently. So the rule here is
conservative: promote only on positive evidence, reject on contradiction, and
send everything in between to a human.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Legal-entity and descriptor noise. Deliberately does NOT include words like
# "space", "energy" or "materials": stripping those would make "Axiom Space"
# and the Axiom Law board both reduce to "axiom" and agree. Stripping less
# means some genuine matches fall to review rather than promote — the cheap
# direction to be wrong in.
_NOISE_RE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|company|holdings|group|"
    r"technologies|technology|labs|systems|solutions|plc|gmbh|pbc|"
    r"industries|ai)\b")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Hosts that are the ATS itself rather than the employer's own site. A posting
# URL on one of these says nothing about whose board it is.
_ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com")


def identity_key(name: str | None) -> str:
    """A company name reduced to what identifies it.

    "Anduril Industries", "Palantir Technologies", "Primer AI" and "Gusto, Inc."
    become "anduril", "palantir", "primer" and "gusto" — so a tracked startup
    matches the Company row that already scans it instead of getting a
    duplicate.
    """
    n = (name or "").lower().replace("&", " and ")
    n = _NON_ALNUM_RE.sub(" ", n)
    n = _NOISE_RE.sub(" ", n)
    return " ".join(n.split())


def site_domain(url: str | None) -> str | None:
    """`https://www.axiomspace.com/careers` -> `axiomspace.com`.

    Naive last-two-labels: right for .com/.io/.tech, wrong for .co.uk. That
    only costs a missed match, which falls to review.
    """
    if not url:
        return None
    u = url if "://" in url else f"https://{url}"
    host = (urlparse(u).hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else None


def _on_ats_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _ATS_HOSTS)


def judge(company: str, website: str | None, board_name: str | None,
          posting_urls: list[str], posting_texts: list[str]) -> tuple[str, str]:
    """("promote" | "reject" | "review", reason).

    Evidence, strongest first:

    1. Postings that link out to the employer's own domain. If we know the
       company's website, that domain either matches (promote) or doesn't
       (reject). This is what catches Axiom Law — its board is named plain
       "Axiom", which would otherwise match.
    2. The board's own display name (Greenhouse has one; Lever and Ashby
       don't). Must equal the company's identity key exactly, so "Watershed
       Informatics" and "Wise Worksite Field Sales" are rejected even though
       each contains the word being looked for.
    3. For boards with no name, the company's full domain appearing in the
       postings — "neon.tech", not the bare word "neon", which a Brazilian
       bank's postings contain constantly.
    """
    target = identity_key(company)
    site = site_domain(website)
    foreign = sorted({d for d in (site_domain(u) for u in posting_urls
                                  if u and not _on_ats_host(u)) if d})

    if site and foreign:
        if site in foreign:
            return "promote", f"postings link to {site}"
        return "reject", f"postings link to {', '.join(foreign)}, not {site}"

    if board_name is not None:
        if identity_key(board_name) != target:
            return "reject", f"board belongs to {board_name!r}"
        if foreign:
            return "review", (f"board name matches, but postings link to "
                              f"{', '.join(foreign)} and there is no website to compare")
        return "promote", "board name matches"

    if site:
        haystack = " ".join(posting_texts + posting_urls).lower()
        if site in haystack:
            return "promote", f"{site} appears in the postings"
        return "review", f"no board name, and {site} never appears in the postings"
    return "review", "no board name and no website to check against"
