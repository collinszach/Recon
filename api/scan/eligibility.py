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
# Mentioning a PhD is not requiring one. The first live run filtered 117 roles
# as "PhD required", including "2027 Summer Intern, MS/PhD, Software/ML" —
# where MS *or* PhD is fine, and his MEng qualifies — and a thermal engineering
# internship whose JD said something like "BS/MS/PhD in Mechanical
# Engineering". A degree list is an invitation, not a gate.
_PHD_WORD = r"ph\.?\s?d\.?"
# In the title, "PhD Research Intern" is the role. "MS/PhD" is not.
_PHD_TITLE_RE = re.compile(rf"(?<!/)(?<!\bms )(?<!\bms/){_PHD_WORD}", re.IGNORECASE)
_DEGREE_LIST_RE = re.compile(rf"\b(bs|ba|ms|meng|mba|master'?s?|bachelor'?s?)\b\s*[/,]?\s*(or\s+)?{_PHD_WORD}",
                             re.IGNORECASE)
# Only explicit requirement phrasing counts as a gate.
_PHD_REQUIRED_RE = re.compile(
    rf"{_PHD_WORD}[^.]{{0,40}}\b(is\s+)?required\b"
    rf"|{_PHD_WORD}[^.]{{0,25}}\b(candidates|students)\s+only\b"
    rf"|\bmust\s+be\s+(enrolled\s+in|pursuing)\b[^.]{{0,30}}{_PHD_WORD}"
    rf"|\bonly\b[^.]{{0,20}}{_PHD_WORD}[^.]{{0,20}}\b(candidates|students)\b",
    re.IGNORECASE)

# Phrasing that turns a requirement back into an invitation.
_PHD_SOFT_RE = re.compile(r"\b(preferred|not required|a plus|nice to have|or equivalent)\b",
                          re.IGNORECASE)

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
    t = title or ""
    body = (description or "")[:4000]
    # Title first: "PhD Research Intern" is what the role is.
    if _PHD_TITLE_RE.search(t) and not _DEGREE_LIST_RE.search(t):
        return "PhD required"
    # In the body, only an explicit requirement counts — and not when it sits
    # in a degree list ("BS/MS/PhD in Mechanical Engineering").
    m = _PHD_REQUIRED_RE.search(body)
    if m:
        window = body[max(0, m.start() - 60):m.end() + 30]
        # "a PhD is preferred but not required" contains the word "required".
        soft = _PHD_SOFT_RE.search(window)
        if not soft and not _DEGREE_LIST_RE.search(window):
            return "PhD required"
    hay = f"{t}\n{body}"
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
