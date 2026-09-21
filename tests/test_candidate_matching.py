"""Tests for local candidate matching and application state transitions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conversation_store import ConversationStore
from matching import match_candidate_to_jobs


class CandidateMatchingTests(unittest.TestCase):
    def test_matching_is_explainable_and_ranked(self) -> None:
        candidate = {"preferred_position": "普工", "preferred_location": "石岩", "skills": "电子 包装"}
        jobs = [
            {"id": 2, "position": "包装工", "location": "深圳市宝安区石岩", "requirements": "手脚灵活", "benefits": "包吃"},
            {"id": 1, "position": "普工", "location": "深圳市宝安区石岩", "requirements": "电子厂经验", "benefits": "包住"},
        ]
        results = match_candidate_to_jobs(candidate, jobs)
        self.assertEqual(results[0]["job"]["id"], 1)
        self.assertIn("岗位方向匹配", results[0]["reasons"])
        self.assertGreater(results[0]["score"], results[1]["score"])

    def test_candidate_phone_is_not_stored_in_plaintext_and_application_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "labor_ai.db")
            candidate_id = store.create_candidate("张三", "13800138000", 25, "男", "石岩", "普工", "电子")
            candidate = store.list_candidates()[0]
            self.assertEqual(candidate["phone_last4"], "8000")
            self.assertNotIn("13800138000", str(candidate))
            with self.assertRaises(ValueError):
                store.create_candidate("李四", "123", 25, "男", "石岩", "普工", "")

            store.sync_jobs_from_file(Path(__file__).resolve().parents[1] / "data" / "jobs.json")
            first = store.create_application(candidate_id, 1)
            second = store.create_application(candidate_id, 1)
            self.assertEqual(first, second)
            self.assertEqual(store.list_applications()[0]["status"], "applied")
            store.update_application_status(first, "interview")
            self.assertEqual(store.list_applications()[0]["status"], "interview")


if __name__ == "__main__":
    unittest.main()
