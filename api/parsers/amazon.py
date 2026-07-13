"""Amazon public jobs API (amazon.jobs).

Endpoint (undocumented but stable, no key):
  GET https://www.amazon.jobs/en/search.json?base_query={term}&result_limit=&offset=

Amazon's board is enormous (tens of thousands of reqs), so rather than page the
whole thing we run the same track-relevant keyword list the Workday backfill and
the search aggregator use, dedup by Amazon's internal job id, and return the
union. That makes this a *sampled* fetch (recall-focused, not the full board),
so `authoritative = False` -> reconcile won't close roles a query happened to
miss. scan.intern_filter's title classifiers still decide what's worth scoring.

`token` is unused (single employer); seed it as None.
"""
from .base import ATSParser, NormalizedRole, client, polite_delay, parse_dt

SEARCH = "https://www.amazon.jobs/en/search.json"
PAGE_SIZE = 100
MAX_PAGES = 2            # per term; politeness cap (Amazon returns up to 100/page)


class AmazonParser(ATSParser):
    ats_name = "amazon"
    authoritative = False       # keyword-sampled, not a full-board dump

    def fetch(self, token: str | None = None) -> list[NormalizedRole]:
        roles: list[NormalizedRole] = []
        seen: set[str] = set()
        with client() as c:
            for term in _terms():
                offset = 0
                for _ in range(MAX_PAGES):
                    resp = c.get(SEARCH, params={
                        "base_query": term,
                        "result_limit": PAGE_SIZE,
                        "offset": offset,
                        "country": "USA",
                    })
                    resp.raise_for_status()
                    data = resp.json()
                    jobs = data.get("jobs") or []
                    for j in jobs:
                        jid = str(j.get("id_icims") or j.get("id") or j.get("job_path"))
                        if not jid or jid in seen:
                            continue
                        seen.add(jid)
                        roles.append(_normalize(j))
                    offset += PAGE_SIZE
                    if offset >= int(data.get("hits") or 0) or len(jobs) < PAGE_SIZE:
                        break
                    polite_delay()
                polite_delay()
        return roles


def _terms() -> list[str]:
    """Track-relevant keyword set, reusing the aggregator's terms plus a couple
    Amazon-flavored ones (TPM is Amazon's dominant PM-adjacent title)."""
    from search import default_terms
    terms = list(default_terms())
    lower = {t.lower() for t in terms}
    for extra in ("technical program manager", "sr product manager"):
        if extra not in lower:
            terms.append(extra)
    return terms


def _normalize(j: dict) -> NormalizedRole:
    path = j.get("job_path") or ""
    loc = j.get("normalized_location") or j.get("location")
    desc = " ".join(x for x in (j.get("description_short"), j.get("basic_qualifications"),
                                j.get("preferred_qualifications")) if x)
    return NormalizedRole(
        ats_job_id=str(j.get("id_icims") or j.get("id") or path),
        title=j.get("title", "Untitled"),
        location=loc,
        remote_flag=bool(loc and "remote" in loc.lower()) or bool(j.get("is_remote")),
        department=j.get("job_category"),
        url=f"https://www.amazon.jobs{path}" if path else None,
        description=f"{loc or ''} {desc}".strip()[:6000],
        posted_at=parse_dt(j.get("posted_date") or j.get("updated_time")),
    )
