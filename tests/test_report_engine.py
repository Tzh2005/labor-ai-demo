"""Tests for delivery metrics and safe evidence export."""

from __future__ import annotations

import json
import unittest

from report_engine import build_evidence_bundle, calculate_delivery_metrics


class ReportEngineTests(unittest.TestCase):
    def test_metrics_do_not_invent_retention_without_history(self) -> None:
        metrics = calculate_delivery_metrics(
            candidates=[{"id": 1}],
            applications=[{"status": "hired"}],
            workers=[{"id": 1}],
            placements=[{"status": "onboarded", "requested_at": "2026-09-20T00:00:00+00:00", "onboarded_at": "2026-09-22T00:00:00+00:00"}],
        )
        self.assertEqual(metrics["average_fill_days"], 2.0)
        self.assertEqual(metrics["placement_fill_rate"], 100.0)
        self.assertIsNone(metrics["retention_7d"])
        self.assertTrue(metrics["limitations"])

    def test_evidence_bundle_excludes_phone_fields(self) -> None:
        payload = build_evidence_bundle(
            project={"id": "demo-project"}, metrics={}, jobs=[],
            candidates=[{"id": 1, "name": "测试工人·张三", "phone_last4": "0001", "phone_hash": "secret"}],
            applications=[], workers=[], placements=[], snapshots=[],
            audit_events=[{"details_json": '{"phone_last4":"0001","status":"created"}'}],
        )
        decoded = json.loads(payload)
        self.assertNotIn("phone_last4", json.dumps(decoded, ensure_ascii=False))
        self.assertNotIn("phone_hash", json.dumps(decoded, ensure_ascii=False))
        self.assertIn("evidence-v1", decoded["schema_version"])


if __name__ == "__main__":
    unittest.main()
