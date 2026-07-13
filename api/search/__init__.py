"""Search-provider registry + default query terms.

enabled_providers() returns only the providers whose credentials are set, so
turning a source on/off is purely a matter of supplying (or omitting) its key.
"""
from config import settings
from search.base import NormalizedRole, SearchProvider, SearchResult
from search.jsearch import JSearchProvider
from search.usajobs import USAJobsProvider
from search.themuse import MuseProvider

_PROVIDERS: list[SearchProvider] = [JSearchProvider(), USAJobsProvider(), MuseProvider()]


def enabled_providers() -> list[SearchProvider]:
    return [p for p in _PROVIDERS if p.enabled()]


def default_terms() -> list[str]:
    """Keyword terms to search. SEARCH_TERMS (.env) overrides; otherwise derive
    a small, free-tier-friendly set from the active tracks."""
    if settings.search_terms.strip():
        return [t.strip() for t in settings.search_terms.split(",") if t.strip()]
    mode = "intern" if settings.intern_only else settings.track_mode
    # Product plus the adjacent families the rubric scores on merit (TPM,
    # solutions/forward-deployed, data/platform eng, devex, autonomy). Plain
    # "software engineer" is deliberately excluded (2026-07-07, Zach's call) —
    # scan.intern_filter.is_pure_swe() also hard-blocks it from every scoring
    # lane regardless of how a role was sourced.
    # The per-run query cap (search_max_queries_per_run) bounds free-tier cost.
    terms = ["product manager", "technical product manager"]
    if mode in ("fulltime", "both"):
        terms += [
            "technical program manager",
            "solutions engineer",
            "forward deployed engineer",
            "data engineer",
            "developer experience",
            "autonomy engineer",
        ]
    if mode in ("intern", "both"):
        terms.append("product manager intern")
    if mode in ("ops", "both"):
        terms.append("strategy and operations")
    return terms


__all__ = ["enabled_providers", "default_terms", "SearchProvider", "SearchResult", "NormalizedRole"]
