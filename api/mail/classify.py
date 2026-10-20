"""What does this message mean, and which application is it about?

Rules, not an LLM. The categories that matter are announced in near-boilerplate
language ("we have decided to move forward with other candidates"), the rules
are auditable, and every proposal carries the phrase that triggered it — which
matters because Zach accepts or rejects each one by hand, and "the model said
so" is not a reason he can check.

Anything the rules can't read confidently comes back as `other` with no
proposed stage, so it shows up as "something arrived" rather than a wrong move.
"""
from __future__ import annotations
import re

# (kind, proposed stage, confidence, patterns). Order matters: a rejection that
# also says "thank you for applying" is a rejection.
RULES: list[tuple[str, str | None, str, list[re.Pattern]]] = [
    ("rejection", "closed", "high", [
        # "not moving forward", "unable to move forward" (Capital One),
        # "decided not to move forward" (Datadog). The first live rules only
        # knew "moving", so both of October's rejections read as nothing.
        # ...but not Amex's draft reminder: "If you choose not to move forward
        # with your application, you may delete it."
        re.compile(r"(?<!choose )(?<!decide )\b(not|unable)\s+(to\s+)?(be\s+)?(mov(e|ing)\s+forward|proceed|progress)", re.I),
        re.compile(r"move\s+forward\s+with\s+(other|another)", re.I),
        re.compile(r"\bunfortunately\b.{0,60}\b(position|role|application|candidat)", re.I),
        # Not bare "decided to move forward" — "...with your candidacy" is the
        # opposite message.
        re.compile(r"\bdecided\s+to\s+(pursue|proceed\s+with|move\s+forward\s+with)\s+(other|another)", re.I),
        re.compile(r"\bno\s+longer\s+under\s+consideration\b", re.I),
        re.compile(r"\bwill\s+not\s+be\s+(moving|progressing)\b", re.I),
    ]),
    ("offer", "offer", "high", [
        re.compile(r"\boffer\s+of\s+(employment|internship)\b", re.I),
        re.compile(r"\bpleased\s+to\s+offer\b", re.I),
        re.compile(r"\bextend(ing)?\s+(you\s+)?an\s+offer\b", re.I),
    ]),
    ("screen", "screen", "high", [
        re.compile(r"\bschedule\s+(a\s+)?(call|time|chat|interview|conversation)", re.I),
        re.compile(r"\b(phone|recruiter|initial)\s+screen\b", re.I),
        re.compile(r"\binterview\s+(invitation|request)\b", re.I),
        re.compile(r"\binvite\s+you\s+to\s+(an?\s+)?(interview|conversation|next)", re.I),
        re.compile(r"\bavailability\b.{0,40}\b(call|interview|chat)\b", re.I),
        re.compile(r"\bbook\s+(a\s+)?time\b", re.I),
        re.compile(r"\bnext\s+steps?\b.{0,40}\binterview\b", re.I),
    ]),
    ("info_request", None, "medium", [
        # Not "survey": Nike's acknowledgement invites you to a tax-credit
        # survey, Waymo's asks for feedback — neither needs anything from you.
        re.compile(r"\b(please\s+)?(complete|fill\s+out)\b.{0,50}\b(assessment|questionnaire|recorded\s+\w+\s+interview)", re.I),
        re.compile(r"\badditional\s+information\s+(is\s+)?(needed|required)\b", re.I),
        re.compile(r"\bwork\s+authorization\s+question", re.I),
        re.compile(r"\bcoding\s+(challenge|assessment)\b", re.I),
    ]),
    ("ack", None, "high", [
        re.compile(r"\b(we|i)\s*('| ha)?ve\s+received\s+your\s+application\b", re.I),
        re.compile(r"\bthank(s|\s+you)\s+(again\s+)?for\s+(applying|your\s+(interest|application|online\s+submission))\b", re.I),
        re.compile(r"\bthank(s|\s+you)\s+for\s+(taking\s+the\s+time\s+to\s+)?(apply|submit)", re.I),
        re.compile(r"\b(successfully\s+applied|completing\s+your\s+application)\b", re.I),
        re.compile(r"\byour\s+application\s+(has\s+been|was)\s+(received|submitted)\b", re.I),
        re.compile(r"\bapplication\s+confirmation\b", re.I),
    ]),
]


def classify(subject: str | None, body: str | None) -> dict:
    """{kind, proposed_stage, confidence, evidence}.

    `ack` deliberately proposes no stage change: an acknowledgement means the
    application arrived, which Recon already knew when Zach marked it applied.
    Moving anything on it would be motion without information.
    """
    hay = f"{subject or ''}\n{body or ''}"
    for kind, stage, confidence, patterns in RULES:
        for pat in patterns:
            m = pat.search(hay)
            if m:
                # Keep the surrounding phrase, not just the match, so the
                # proposal can show why in words Zach can judge.
                start, end = max(0, m.start() - 40), min(len(hay), m.end() + 40)
                phrase = re.sub(r"\s+", " ", hay[start:end]).strip()
                return {"kind": kind, "proposed_stage": stage,
                        "confidence": confidence, "evidence": f"…{phrase}…"}
    return {"kind": "other", "proposed_stage": None, "confidence": "low",
            "evidence": "no recognised phrasing; shown so it isn't missed"}


# The role, as the employer wrote it. Accepting a proposal used to title the
# new application with the email subject, which is how the pipeline filled up
# with roles called "Thank you for applying to Relay!" — and why Recon could
# not tell Intuit's TPM application from its Product Manager one.
_ROLE_RES = [
    # "...role: Product Management Intern, Summer 2027 - United States ." (Mastercard)
    re.compile(r"\bfor\s+the\s+(?:role|position):?\s+(?P<t>[^.!]{4,140}?)\s*(?:\s-\s(?:United States|New York)|\s\.|\.\s|\.$)", re.I),
    # "...application for Business Program Management INTERN (Job number: 200058904)"
    re.compile(r"\bapplication\s+for\s+(?:the\s+)?(?P<t>[^.!()]{4,140}?)\s*\((?:job|req)", re.I),
    # "...apply for the Summer 2027: MBA Strategy & Operations Intern position"
    # "...applying to the AI Product Manager - MBA Intern (Summer 2027) role"
    # "...interest in the Product Management Intern, 2027 Summer U.S. position"
    re.compile(r"\b(?:appl(?:y|ying|ied|ication)|interest|submission)\s+(?:to|for|in)\s+(?:the\s+|our\s+)?"
               r"(?:position\s+(?:of\s+)?)?(?P<t>[^.!]{4,140}?)\s+(?:role|position|opening|job)\b", re.I),
    # "Your application for Technical Program Manager Intern (Summer 2027) has been received"
    re.compile(r"\bapplication\s+for\s+(?:the\s+)?(?P<t>[^.!]{4,140}?)\s+(?:has|was|is)\b", re.I),
    # "...has been received for Associate Product Manager, Intern." (Duolingo)
    re.compile(r"\breceived\s+for\s+(?:the\s+)?(?P<t>[^.!]{4,140}?)\.", re.I),
    # "...apply for GE Vernova Controls Product Management Intern - Summer 2027 ." —
    # Workday templates leave a space before the full stop.
    re.compile(r"\bapply\s+for\s+(?:the\s+)?(?P<t>[^.!]{4,140}?)\s\.", re.I),
    # Subject: "Update on your Skydio Application - Operations Program Management Intern"
    re.compile(r"\bapplication\s+[-–:]\s+(?P<t>[^!]{4,140}?)\s*$", re.I),
    # Subject: "Your application to 2027 Summer Intern - Digital Product ... is in!" (GM)
    re.compile(r"\bapplication\s+to\s+(?P<t>[^!]{4,140}?)\s+is\s+in\b", re.I),
]
# A lazy match starts at the FIRST trigger, so "interest in C3 AI and for
# applying to the AI Product Manager role" captures the company too. Keep what
# follows the last trigger inside the capture.
_INNER_TRIGGER = re.compile(r".*\b(?:appl(?:y|ying|ied|ication)\s+(?:to|for)|and\s+the|"
                            r"for\s+the|in\s+the)\s+(?:the\s+|our\s+)?", re.I)
_REQ_PREFIX = re.compile(r"^(?:[A-Z]{0,3}\d{5,}\s+)")          # "R171856 ", "JR2025670 ", "128509 "
_REQ_SUFFIX = re.compile(r"\s*(?:[-–]\s*\d{5,}|\(\d{5,}\))$")  # "... - 3095762", "(26107924)"
_LOCATION_SUFFIX = re.compile(r"\s+[-–]\s+[A-Z][\w .]+,\s+[A-Z]{2}(?:,\s*US)?$")  # "... – New York City, NY, US"
# "fit for the position we will contact you soon" is not a role (Muon, Zipline).
_NOT_A_ROLE = re.compile(r"^(?:a|an|this|that|our|your|the)\b|\b(?:company|team|careers?|we|you|will)\b", re.I)


def role_title(subject: str | None, body: str | None) -> str | None:
    """Role title out of application mail, or None when it isn't stated."""
    for text in (body or "", subject or ""):
        flat = re.sub(r"\s+", " ", text.replace("&amp;", "&"))
        flat = re.sub(r"\b(Inc|Corp|Ltd|Co)\.", r"\1", flat)     # "[^.]" must survive "NIKE, Inc."
        for pat in _ROLE_RES:
            m = pat.search(flat)
            if not m:
                continue
            t = _INNER_TRIGGER.sub("", m.group("t")).strip(" :-–,\"'")
            t = re.sub(r"^(?:of\s+|[\w&]+'s\s+)", "", t)          # "position of X", "DoorDash's X"
            t = re.sub(r"^[A-Z][\w&]*,?\s+Inc\s+", "", t)          # "NIKE, Inc. Digital Growth ..."
            t = _LOCATION_SUFFIX.sub("", _REQ_SUFFIX.sub("", _REQ_PREFIX.sub("", t))).strip(" -–,")
            if 4 <= len(t) <= 140 and not _NOT_A_ROLE.search(t):
                return t
    return None


_ROLE_STOP = {"intern", "internship", "summer", "the", "and", "of", "for", "a", "an",
              "us", "u", "s", "united", "states", "2026", "2027", "2028", "mba",
              "program", "opportunities", "graduate", "masters"}
# Titles the old accept path copied from email subjects.
_PLACEHOLDER = re.compile(r"^(thank|thanks|your application|application|you have|"
                          r"successfully|we got|invitation|update)\b", re.I)


def placeholder_title(title: str | None) -> bool:
    """True when an application's 'role' is really an email subject, or empty."""
    return not title or bool(_PLACEHOLDER.search(title.strip()))


def same_role(a: str | None, b: str | None) -> bool:
    """Do two titles name the same role? Loose on purpose.

    Employers word a role differently in the posting, the confirmation and the
    rejection ("Product Management Intern, 2027 Summer U.S." vs "Product
    Management Intern"), so this compares the distinctive words and calls it
    the same when one title's words are almost all in the other. What it must
    not do is merge Intuit's TPM application into its Product Manager one.
    """
    def words(t):
        # Six-letter stems: "Manager" and "Management" are the same word here.
        return {w[:6] for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if w not in _ROLE_STOP}
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    # Overlap over the union, not the smaller set: "Product Manager:
    # Internship Opportunities" is wholly contained in "Product Management
    # Intern - CTJ - TS with Security Clearance", and they are not one role.
    return len(wa & wb) / len(wa | wb) >= 0.5
