"""Pure-logic checks for the classifiers. No DB, no network, no dependencies.

Every case here is one that actually went wrong, or one whose breaking would
be silent and expensive. Run: `python3 api/tests/test_logic.py`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mail.classify import classify                      # noqa: E402
from scan.geo import is_us, metro_of, states_of         # noqa: E402
from scan.intern_filter import in_active_track, is_internship, is_pure_swe  # noqa: E402

failures: list[str] = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")


# ── geo ────────────────────────────────────────────────────────────────────
# A Netherlands office written "Amsterdam, NH" must not parse as New Hampshire.
check("amsterdam-nh", states_of("Amsterdam, NH"), ["international"])
# A multi-city posting must keep every state, and must not lose its US leg to
# an international hint in another segment.
check("multi-city", states_of("Atlanta, GA; London, UK"), ["GA", "international"])
check("multi-city-us", is_us("Atlanta, GA; London, UK", "GA,international"), True)
# Bare cities and Adzuna's county form.
check("bare-city", states_of("San Francisco"), ["CA"])
check("county-form", states_of("Pittsburgh, Allegheny County"), ["PA"])
check("amazon-prefix", states_of("US-CA-Menlo Park"), ["CA"])
check("metro", metro_of("Sunnyvale"), "bay_area")
# Ambiguous cities stay unresolved rather than being guessed.
for city in ("Portland", "Columbus", "Springfield"):
    check(f"ambiguous-{city}", states_of(city), [])
# US-only filtering, including the title as last resort.
check("intl-title", is_us(None, None, "Internship – Strategy Luxembourg"), False)
check("us-unparseable", is_us("TAURUS", None, "Analyst, New York"), True)
check("location-wins", is_us("Boston, MA", "MA", "Hamburg Steel Account"), True)

# ── track classification ───────────────────────────────────────────────────
check("swe-intern-excluded", in_active_track("Software Engineering Intern, Android", None, "intern"), False)
check("pm-intern-included", in_active_track("Product Management Intern", None, "intern"), True)
check("is-internship", is_internship("Summer 2027 Intern, Operations"), True)
check("pure-swe", is_pure_swe("Senior Software Engineer"), True)
# Full-time roles must not leak into an intern-only feed.
check("fulltime-excluded", in_active_track("Senior Product Manager", None, "intern"), False)

# ── mail classification ────────────────────────────────────────────────────
def kind(subject, body=""):
    return classify(subject, body)["kind"]


check("ack", kind("Thank you for applying to Databricks!"), "ack")
check("rejection", kind("Update", "we have decided to move forward with other candidates"), "rejection")
check("rejection-2", kind("Update", "we will not be moving forward with your candidacy"), "rejection")
check("screen", kind("Next steps", "we would like to schedule a call with our recruiter"), "screen")
check("offer", kind("Good news", "we are pleased to offer you the position"), "offer")
check("assessment", kind("Action required", "please complete the online assessment"), "info_request")
# A newsletter must propose nothing — the guard against a tracker that lies.
check("newsletter", kind("Weekly digest", "five articles about product management"), "other")
check("newsletter-no-stage", classify("Weekly digest", "articles")["proposed_stage"], None)
# An acknowledgement proposes no stage on its own; the poller decides that
# against the application's current stage.
check("ack-no-stage", classify("Thank you for applying", "")["proposed_stage"], None)

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all logic checks passed")

# ── eligibility / target (appended 2026-09-22) ─────────────────────────────
from scan.eligibility import eligibility_reason, off_target_reason  # noqa: E402

check("phd", eligibility_reason("PhD Research Intern", "PhD candidates only"), "PhD required")
check("phd-preferred-ok", eligibility_reason("Product Intern", "PhD preferred but not required"), None)
check("sophomore", eligibility_reason("2027 Sophomore Internship Program"), "undergraduate-only program")
check("clearance", eligibility_reason("PM Intern", "Must currently hold an active TS/SCI clearance"),
      "requires an existing security clearance")
# A clearance the employer sponsors is not a gate — he already tracks one.
check("clearance-sponsored", eligibility_reason("PM Intern", "Ability to obtain a security clearance"), None)
check("keep-pm", off_target_reason("Product Management Intern - Summer 2027"), None)
check("keep-tpm", off_target_reason("Technical Program Manager Intern"), None)
check("keep-strategy", off_target_reason("Business Strategy & Operations Intern"), None)
check("drop-mech", off_target_reason("Mechanical Engineering Intern"), "not a product/strategy role")
check("drop-clinical", off_target_reason("Clinical Operations Intern"), "not a product/strategy role")

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all logic checks passed (including eligibility)")
