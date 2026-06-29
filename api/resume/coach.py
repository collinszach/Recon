"""Interactive résumé coach — a collaborative chat that helps Zach refine his
resume. Discusses, coaches, asks when unsure, and proposes concrete edits the
human applies. Never fabricates; keeps the resume to one page; keeps Zach's voice
(not AI-sounding)."""
import json
import logging
from sqlalchemy.orm import Session
import llm
from config import settings
from db import Role  # noqa: F401 (kept for parity / future role-aware coaching)
from resume.tailor import assemble_resume

log = logging.getLogger("recon.coach")

SYSTEM = """\
You are Zach Collins's personal résumé coach. This is a COLLABORATIVE working session — talk with
him like a sharp mentor, not a form. Help him discuss, sharpen, and update his resume.

Hard rules:
- NEVER invent or embellish. Use only what's in his resume or what HE tells you in the chat. If a
  detail (a metric, a date, a scope) is missing or unclear, ASK him — don't guess or pad.
- Keep the resume to ONE PAGE. If adding something pushes it long, suggest what to cut or tighten.
- Keep HIS voice — it must NOT read like AI wrote it. Avoid résumé-clichés and AI tells:
  "spearheaded", "leveraged", "passionate", "results-driven", "synergy", "in today's fast-paced",
  "robust", "seamless", "utilize", and em-dash-stuffed sentences. Prefer plain, specific, verifiable
  language and strong concrete verbs (built, shipped, led, cut, owned, migrated).
- Be concise and conversational. Coach: point out what's strong, what's weak, what's missing.
- When you and he have settled on a concrete change, propose it in `proposed_update` so he can
  apply it with one tap. Otherwise leave it null and keep talking / asking.

Respond with ONLY a JSON object (no prose outside it, no code fences):
{
  "reply": "<your conversational message to Zach>",
  "proposed_update": null OR {
    "summary": "<one line describing the change you're proposing>",
    "profile": null OR { any of: full_name, headline, location, summary, skills, education, links },
    "experience": null OR { "id": <int to edit, or null to ADD>, "kind": "work|project|leadership",
                            "company": "...", "title": "...", "location": "...",
                            "start_date": "...", "end_date": "...", "bullets": "<newline-separated>" }
  }
}
Only fill `proposed_update` when there is a specific, ready edit — never speculatively.
"""


def coach_reply(db: Session, messages: list[dict]) -> dict:
    resume = assemble_resume(db)
    if not resume:
        return {"reply": "There's no resume loaded yet — add one in the Résumé tab and we can start.",
                "proposed_update": None}
    if settings.scoring_mode != "live" or not llm.configured():
        return {"reply": "Coaching needs the live AI (SCORING_MODE=live + an LLM backend configured).",
                "proposed_update": None}

    convo = [{"role": ("assistant" if m.get("role") == "assistant" else "user"),
              "content": m.get("content", "")} for m in messages if m.get("content")]
    if not convo:
        convo = [{"role": "user", "content": "Let's review my resume. Where should I start?"}]
    # Ground the model in the current resume on the first user turn.
    convo[0] = {"role": "user",
                "content": f"=== MY CURRENT RESUME ===\n{resume}\n\n=== MESSAGE ===\n{convo[0]['content']}"}

    res = llm.complete(system=SYSTEM, max_tokens=1200, messages=convo)
    text = res.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            text = text[a:b + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("coach: unparseable reply: %r", text[:300])
        return {"reply": text or "Sorry, try rephrasing that.", "proposed_update": None}
    data.setdefault("proposed_update", None)
    return data
