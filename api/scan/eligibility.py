"""Should Zach apply to this, and could he if he wanted to?

Two different questions, kept apart on purpose:

- **Eligibility** — a hard gate the posting itself sets. A PhD requirement or a
  sophomore-only program is a fact about the role, not a matter of taste.
- **Target family** — whether it's the kind of work he's looking for. He asked
  to keep "strategy, pm, tpm, etc.", so this is an allowlist: a role has to
  look like product, program, strategy, operations or data work to pass.

Both give a *reason*, because a feed that silently drops things is how you miss
the one you wanted. The API returns the reason so the app can show what it hid.

Profile this is written against (from his résumé, on file): MBA (Berkeley Haas)
+ MEng, May 2028; B.S. Mechanical Engineering 2023. So: a graduate student, not
an undergraduate, no PhD, no active clearance.
"""
from __future__ import annotations
import re

# ── hard eligibility gates ──────────────────────────────────────────────────
_PHD_RE = re.compile(
    r"\b(ph\.?\s?d\.?|doctoral|doctorate)\b(?![^.]{0,40}\b(not required|or equivalent experience|preferred)\b)",
    re.IGNORECASE)
# "PhD preferred" is not a gate; "PhD required"/"PhD candidates" is.
_PHD_SOFT_RE = re.compile(r"\bph\.?\s?d\.?\b[^.]{0,30}\b(preferred|a plus|nice to have)\b", re.IGNORECASE)

_UNDERGRAD_ONLY_RE = re.compile(
    r"\b(sophomore|freshman|first[- ]year student|rising (freshman|sophomore|junior))\b"
    r"|\bundergraduate(s)? only\b|\bmust be (a|an) undergraduate\b"
    r"|\bbachelor'?s? (students|candidates) only\b", re.IGNORECASE)

# An EXISTING clearance is a gate. One the employer will sponsor is not — he
# already has a TS-cleared Microsoft role in his pipeline.
_CLEARANCE_RE = re.compile(
    r"\b(active|current|existing)\s+(ts/sci|top secret|secret|security)\s*clearance\b"
    r"|\bmust (currently )?(possess|hold|have)\b[^.]{0,40}\bclearance\b"
    r"|\bclearance\s+is\s+required\s+(at|prior to)\s+(start|hire)\b", re.IGNORECASE)
_CLEARANCE_SPONSORED_RE = re.compile(
    r"\b(ability|able) to obtain\b[^.]{0,30}\bclearance\b|\bwill sponsor\b[^.]{0,30}\bclearance\b"
    r"|\bclearance\s+(is\s+)?(sponsored|not required)\b", re.IGNORECASE)

# ── the work he's actually looking for ──────────────────────────────────────
_TARGET_RE = re.compile(
    r"\b(product manage|product management|product manager|\bapm\b|associate product|"
    r"technical program|program manage|program manager|\btpm\b|project manage|"
    r"product owner|product operations|product strategy|product analyst|product design|"
    r"strategy|strategic|business development|corporate development|"
    r"business operations|bizops|business analyst|operations manage|operations analyst|"
    r"supply chain|logistics|go[- ]to[- ]market|growth|"
    r"data analyst|data science|analytics|business intelligence|"
    r"consult|mba|solutions|customer success|partnerships|"
    r"technical product|platform product|ai product)\b", re.IGNORECASE)

# Disciplines that read as target words but aren't the work — "clinical
# operations" is not business operations.
_TARGET_FALSE_RE = re.compile(
    r"\b(clinical|nursing|nurse|pharmac|laboratory|lab technician|phlebotom|"
    r"veterinar|dental|therapy|therapist|counsel|social work|"
    r"warehouse associate|forklift|driver|custodial|"
    r"tax|audit|actuarial|accounting|payroll|"
    r"mechanical design|electrical design|structural|hvac|welding|machinist)\b",
    re.IGNORECASE)


def eligibility_reason(title: str | None, description: str | None = None) -> str | None:
    """Why he *can't* apply, or None. Checked against title + JD text."""
    hay = f"{title or ''}\n{(description or '')[:4000]}"
    if _PHD_RE.search(hay) and not _PHD_SOFT_RE.search(hay):
        return "PhD required"
    if _UNDERGRAD_ONLY_RE.search(hay):
        return "undergraduate-only program"
    if _CLEARANCE_RE.search(hay) and not _CLEARANCE_SPONSORED_RE.search(hay):
        return "requires an existing security clearance"
    return None


def off_target_reason(title: str | None, department: str | None = None) -> str | None:
    """Why it isn't the work he's looking for, or None.

    An allowlist: product / program / strategy / operations / data / consulting.
    Anything else is off-target — including the mechanical and lab internships
    his degree would technically qualify him for.
    """
    hay = " ".join(p for p in (title, department) if p)
    if not hay:
        return None
    if _TARGET_FALSE_RE.search(hay):
        return "not a product/strategy role"
    if _TARGET_RE.search(hay):
        return None
    return "not a product/strategy role"
