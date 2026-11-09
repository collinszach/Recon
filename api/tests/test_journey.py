"""Offline reconciliation journey; run directly in a fresh Python process.

Uses real ORM models and journey functions, SQLite memory storage, and fixed
configuration instead of reading host environment files. No ATS or LLM calls.
"""
import sys
import subprocess
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

def _run_journey():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # Install before importing application modules: never construct a host DB engine
    # or load credentials from .env. These are the only settings this journey uses.
    config = types.ModuleType("config")
    config.settings = types.SimpleNamespace(
        database_url="sqlite+pysqlite:///:memory:",
        scoring_mode="stub", intern_target_year=2027,
    )
    sys.modules["config"] = config

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from db import Base, Company, Role, Application, DailyBrief, engine
    from parsers.base import NormalizedRole
    from scan.reconcile import reconcile_company
    from scoring.claude_scorer import score_roles
    from brief.generator import build_brief


    def posting(key, title="Product Manager", description="Synthetic platform work"):
        return NormalizedRole(key, title, location="Boston, MA",
                              url=f"https://example.invalid/jobs/{key}",
                              description=description)


    class JourneyTest(unittest.TestCase):
        def setUp(self):
            Base.metadata.create_all(engine)
            self.db = Session(engine)
            self.company = Company(name="Synthetic Journey Company", tier="A")
            self.db.add(self.company)
            self.db.commit()
            # Any accidental network access is a failure, including LLM calls.
            self.network = patch("socket.socket.connect", side_effect=AssertionError("network forbidden"))
            self.network.start()
            self.llm = patch("llm.complete", side_effect=AssertionError("LLM forbidden"))
            self.llm.start()

        def tearDown(self):
            self.llm.stop()
            self.network.stop()
            self.db.close()
            Base.metadata.drop_all(engine)

        def reconcile(self, postings, **kwargs):
            return reconcile_company(self.db, self.company.id, postings, **kwargs)

        def roles(self):
            return {r.ats_job_id: r for r in self.db.scalars(select(Role))}

        def test_reconciliation_scoring_brief_and_application(self):
            first = self.reconcile([posting("keep"), posting("change"),
                                    posting("close", "Technical Program Manager")])
            self.assertEqual((first["new"], first["changed"], first["closed"]), (3, 0, 0))
            roles = self.roles()
            original_ids = {key: role.id for key, role in roles.items()}
            self.assertEqual(set(first["new_ids"]), set(original_ids.values()))
            score_roles(self.db, list(roles.values()))
            self.assertTrue(all(r.scored_at is not None for r in roles.values()))

            snapshot = [posting("keep"), posting("change", "Platform Product Manager",
                        "Synthetic revised requirements"), posting("new")]
            totals = self.reconcile(snapshot)
            self.assertEqual((totals["new"], totals["changed"], totals["closed"]), (1, 1, 1))
            roles = self.roles()
            self.assertEqual(totals["changed_ids"], [original_ids["change"]])
            self.assertEqual(totals["new_ids"], [roles["new"].id])
            self.assertEqual(roles["keep"].id, original_ids["keep"])
            self.assertEqual(roles["change"].status, "changed")
            self.assertIsNone(roles["change"].scored_at)
            self.assertEqual(roles["change"].description, "Synthetic revised requirements")
            self.assertEqual(roles["close"].status, "closed")
            self.assertIsNone(roles["new"].posted_at)  # unknown stays unknown
            cost = score_roles(self.db, [roles["change"], roles["new"]])
            self.assertEqual(cost, {"tokens_in": 0, "tokens_out": 0, "usd": 0.0})
            self.assertIsNotNone(roles["change"].scored_at)

            today = date(2026, 11, 9)
            brief = build_brief(self.db, today, totals)
            self.assertIn("Platform Product Manager", brief.markdown)
            self.assertNotIn("Technical Program Manager", brief.markdown)
            self.assertIn("Heuristic stub score", brief.markdown)
            self.assertEqual(brief.new_count, 1)
            role = roles["new"]
            self.db.add(Application(role_id=role.id, company_name=self.company.name,
                                    role_title=role.title, role_url=role.url,
                                    stage="watching"))
            self.db.commit()
            updated = build_brief(self.db, today, totals)
            self.assertEqual(updated.id, brief.id)
            self.assertIn("Watching 1", updated.markdown)
            self.assertEqual(self.db.scalar(select(func.count()).select_from(DailyBrief)), 1)
            self.db.expire_all()
            application = self.db.scalar(select(Application))
            self.assertEqual(application.role.ats_job_id, "new")
            self.assertEqual(application.stage, "watching")
            repeated = self.reconcile(snapshot)
            self.assertEqual((repeated["new"], repeated["changed"], repeated["closed"]), (0, 0, 0))
            self.assertEqual(self.db.scalar(select(func.count()).select_from(Role)), 4)

        def test_partial_and_empty_boards(self):
            self.reconcile([posting("a"), posting("b")], backfill=True)
            self.assertTrue(all(r.is_backfill for r in self.roles().values()))
            sampled = self.reconcile([posting("a")], close_missing=False)
            self.assertEqual(sampled["closed"], 0)
            self.assertEqual(self.roles()["b"].status, "open")
            self.assertEqual(self.reconcile([])["closed"], 2)
            self.assertEqual(self.reconcile([])["closed"], 0)
            reopened = self.reconcile([posting("b")])
            self.assertEqual(reopened["new"], 0)
            self.assertEqual(self.roles()["b"].status, "open")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(JourneyTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


class OfflineJourneyTest(unittest.TestCase):
    def test_isolated_journey(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout + result.stderr, end="")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        sys.exit(_run_journey())
    unittest.main(verbosity=2)
