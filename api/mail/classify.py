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
        re.compile(r"\b(not|unable to)\s+(be\s+)?(moving|proceed|progress)", re.I),
        re.compile(r"move\s+forward\s+with\s+other", re.I),
        re.compile(r"\bunfortunately\b.{0,60}\b(position|role|application|candidat)", re.I),
        re.compile(r"\bwe('| ha)ve\s+decided\s+to\s+(pursue|move)", re.I),
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
        re.compile(r"\b(please\s+)?(complete|fill\s+out|submit)\b.{0,50}\b(assessment|form|questionnaire|survey)", re.I),
        re.compile(r"\badditional\s+information\s+(is\s+)?(needed|required)\b", re.I),
        re.compile(r"\bwork\s+authorization\s+question", re.I),
        re.compile(r"\bcoding\s+(challenge|assessment)\b", re.I),
    ]),
    ("ack", None, "high", [
        re.compile(r"\b(we|i)\s*('| ha)?ve\s+received\s+your\s+application\b", re.I),
        re.compile(r"\bthank\s+you\s+for\s+(applying|your\s+(interest|application))\b", re.I),
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
