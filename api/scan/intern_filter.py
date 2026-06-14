"""Internship classifier — keeps the pipeline focused on Zach's Summer 2027
internship hunt instead of the full-time firehose.

Whether a posting is an internship is decided from its TITLE (+ department),
which is reliable; descriptions add too many false positives ("our interns…",
"international", "internal tools"). The scorer (claude_scorer) handles the finer
judgement of *which* internship — product vs program, right summer term, fit.

Pure stdlib so it can run in the worker or be unit-tested without the app.
"""
import re

# Word-boundary signals that a title is an internship / co-op / summer program.
_INTERN_RE = re.compile(
    r"\b("
    r"intern|interns|internship|internships|"
    r"co-?op|"
    r"summer\s+(?:associate|analyst|scholar)|"
    r"mba\s+(?:intern|associate)|"
    r"apprentice|apprenticeship|"
    r"graduate\s+intern|phd\s+intern|"
    r"early\s+career\s+intern"
    r")\b",
    re.IGNORECASE,
)

# Guard against "intern" embedded in unrelated words the boundary check misses
# in some locales (e.g. hyphenation). These are NOT internships.
_FALSE_POSITIVE_RE = re.compile(
    r"\b(internal|international|internalization|alternate|alternating)\b",
    re.IGNORECASE,
)


def is_internship(title: str | None, department: str | None = None) -> bool:
    """True if the posting looks like an internship / co-op / summer program."""
    hay = " ".join(p for p in (title, department) if p)
    if not hay:
        return False
    if not _INTERN_RE.search(hay):
        return False
    # If the only match came from a false-positive word, reject.
    cleaned = _FALSE_POSITIVE_RE.sub(" ", hay)
    return bool(_INTERN_RE.search(cleaned))


def filter_internships(roles: list) -> list:
    """Subset a list of Role-like objects (with .title/.department) to interns."""
    return [r for r in roles if is_internship(getattr(r, "title", None),
                                              getattr(r, "department", None))]


# ── Full-time product-management roles ──────────────────────────────────────
# Pre-narrow to likely product-PM titles so we don't score the whole firehose.
# The scorer's full-time rubric then makes the finer product-vs-program call.
_PM_RE = re.compile(
    r"\b("
    r"product\s+manager(s)?|"
    r"product\s+management|"
    r"product\s+owner|"
    r"product\s+lead|"
    r"lead\s+product\s+manager|"
    r"group\s+product\s+manager|"
    r"(senior|sr\.?|staff|principal|lead|associate)\s+product\s+manager|"
    r"head\s+of\s+product|"
    r"(director|vp|vice\s+president)\s*(of|,)?\s*product|"
    r"chief\s+product\s+officer|"
    r"\bcpo\b"
    r")\b",
    re.IGNORECASE,
)
# Things that contain "product …" but are NOT product management.
_PM_FALSE_RE = re.compile(
    r"\b(product\s+marketing|product\s+design(er)?|production|"
    r"product\s+analyst|product\s+support|product\s+specialist|"
    r"product\s+counsel|product\s+security|technical\s+program)\b",
    re.IGNORECASE,
)


def is_fulltime_pm(title: str | None, department: str | None = None) -> bool:
    """True for a full-time product-management role (not an internship)."""
    hay = " ".join(p for p in (title, department) if p)
    if not hay or is_internship(title, department):
        return False
    if _PM_FALSE_RE.search(hay):
        # reject only if the false term is the sole product mention
        if not _PM_RE.search(_PM_FALSE_RE.sub(" ", hay)):
            return False
    return bool(_PM_RE.search(hay))


def filter_fulltime_pm(roles: list) -> list:
    return [r for r in roles if is_fulltime_pm(getattr(r, "title", None),
                                               getattr(r, "department", None))]


# ── Operations / strategy roles (Zach is open to ops; founder/CTO/COO path) ──
_OPS_RE = re.compile(
    r"\b("
    r"chief\s+of\s+staff|"
    r"business\s+operations|biz\s*ops|"
    r"strateg(y|ic)\s*(and|&|,)?\s*(operations|ops)|"
    r"(operations|ops)\s*(and|&|,)?\s*strateg(y|ic)|"
    r"revenue\s+operations|rev\s*ops|"
    r"corporate\s+(strategy|development)|corp\s+dev|"
    r"business\s+strategy|"
    r"go-?to-?market\s+strateg(y|ic)|gtm\s+strateg(y|ic)|"
    r"general\s+manager|"
    r"(strategy|strategic)\s+(manager|lead|director|principal|associate|analyst|partner)|"
    r"head\s+of\s+(strategy|operations|business\s+operations)|"
    r"(vp|vice\s+president|director|head)\s*(of)?\s*(business\s+operations|strategy)"
    r")\b",
    re.IGNORECASE,
)
# Operations roles that are NOT the biz/strategy kind we want.
_OPS_FALSE_RE = re.compile(
    r"\b(security\s+operations|network\s+operations|it\s+operations|noc\b|soc\s+analyst|"
    r"clinical\s+operations|flight\s+operations|manufacturing\s+operations|"
    r"warehouse\s+operations|field\s+operations|trading\s+operations)\b",
    re.IGNORECASE,
)


def is_ops_strategy(title: str | None, department: str | None = None) -> bool:
    """True for a business-operations / strategy / GM / chief-of-staff role
    (not an internship, not the excluded technical/field-ops kinds)."""
    hay = " ".join(p for p in (title, department) if p)
    if not hay or is_internship(title, department):
        return False
    if _OPS_FALSE_RE.search(hay) and not _OPS_RE.search(_OPS_FALSE_RE.sub(" ", hay)):
        return False
    return bool(_OPS_RE.search(hay))


def filter_ops_strategy(roles: list) -> list:
    return [r for r in roles if is_ops_strategy(getattr(r, "title", None),
                                                getattr(r, "department", None))]
