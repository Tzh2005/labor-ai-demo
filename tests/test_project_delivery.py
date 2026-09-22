"""Tests for project delivery metrics, evidence and deterministic risk rules."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conversation_store import ConversationStore
from risk_engine import assess_project_risks


class ProjectDeliveryTests(unittest.TestCase):
    def test_audit_events_form_a_hash_chain_and_worker_lifecycle_is_traceable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "labor_ai.db")
            candidate_id = store.create_candidate("张三", "13800138000", 25, "男", "石岩", "普工", "包装")
            store.sync_jobs_from_file(Path(__file__).resolve().parents[1] / "data" / "jobs.json")
            worker_id = store.promote_candidate_to_worker(candidate_id)
            placement_id = store.create_placement(worker_id, 1)
            store.update_placement_status(placement_id, "onboarded")
            events = list(reversed(store.list_audit_events()))
            self.assertGreaterEqual(len(events), 4)
            for previous, current in zip(events, events[1:]):
                self.assertEqual(current["previous_hash"], previous["event_hash"])
            self.assertEqual(store.list_workers()[0]["lifecycle_status"], "onboarded")
            self.assertEqual(store.list_placements()[0]["status"], "onboarded")

    def test_risk_rules_prioritize_stale_applications_and_unfilled_jobs(self) -> None:
        now = datetime.now(timezone.utc)
        risks = assess_project_risks(
            jobs=[{"id": 1, "factory_name": "甲厂", "position": "普工"}, {"id": 2, "factory_name": "乙厂", "position": "包装工"}],
            applications=[{"job_id": 1, "name": "张三", "factory_name": "甲厂", "position": "普工", "status": "applied", "created_at": (now - timedelta(days=10)).isoformat()}],
            placements=[],
            now=now,
        )
        self.assertEqual(risks[0]["code"], "stale_application")
        self.assertIn("no_candidate", {risk["code"] for risk in risks})


if __name__ == "__main__":
    unittest.main()
