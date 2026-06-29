"""Search-source interface — third-party job aggregators (JSearch, USAJobs).

Unlike parsers/ (per-company ATS endpoints keyed by an ats_token), a search
provider returns roles from MANY employers for a keyword query. Each result
carries the employer name; scan/search_runner.py upserts a Company per employer
and ingests WITHOUT the 'close missing' step (a search result set is a sampled
slice, not an authoritative company board). Providers reuse parsers.base's
NormalizedRole so downstream scoring/geo/track code is unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass

from parsers.base import NormalizedRole


@dataclass
class SearchResult:
    employer: str
    role: NormalizedRole


class SearchProvider:
    """Subclass and implement enabled() + search()."""
    name: str = "base"

    def enabled(self) -> bool:
        """True when the provider has the credentials it needs."""
        raise NotImplementedError

    def search(self, term: str) -> list[SearchResult]:
        """Return roles for a keyword term (nationwide; the caller geo-filters)."""
        raise NotImplementedError
