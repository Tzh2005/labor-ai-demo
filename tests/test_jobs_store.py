"""Tests for the first structured jobs-data migration step."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from conversation_store import ConversationStore


class JobsStoreTests(unittest.TestCase):
    def test_sync_is_idempotent_and_preserves_legacy_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "labor_ai.db"
            jobs_path = root / "jobs.json"
            jobs = [{
                "id": 1,
                "factory_name": "测试工厂",
                "position": "普工",
                "salary": "5000-6000元/月",
                "requirements": "18岁以上",
                "benefits": "包吃",
                "work_time": "白班",
                "location": "深圳市宝安区",
                "overtime": "按规定",
            }]
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")

            store = ConversationStore(database_path)
            self.assertEqual(store.sync_jobs_from_file(jobs_path), 1)
            self.assertEqual(store.sync_jobs_from_file(jobs_path), 1)
            self.assertEqual(store.job_count(), 1)
            self.assertEqual(store.list_jobs(location="宝安", position="普工"), jobs)

    def test_sync_removes_jobs_deleted_from_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs_path = root / "jobs.json"
            jobs_path.write_text(json.dumps([
                {"id": 1, "factory_name": "甲", "position": "普工", "salary": "1", "requirements": "1", "benefits": "1", "work_time": "1", "location": "甲地", "overtime": "1"},
                {"id": 2, "factory_name": "乙", "position": "普工", "salary": "2", "requirements": "2", "benefits": "2", "work_time": "2", "location": "乙地", "overtime": "2"},
            ], ensure_ascii=False), encoding="utf-8")
            store = ConversationStore(root / "labor_ai.db")
            store.sync_jobs_from_file(jobs_path)
            jobs_path.write_text(json.dumps([{
                "id": 1,
                "factory_name": "甲",
                "position": "普工",
                "salary": "1",
                "requirements": "1",
                "benefits": "1",
                "work_time": "1",
                "location": "甲地",
                "overtime": "1",
            }], ensure_ascii=False), encoding="utf-8")
            self.assertEqual(store.sync_jobs_from_file(jobs_path), 1)
            self.assertEqual([job["id"] for job in store.list_jobs()], [1])


if __name__ == "__main__":
    unittest.main()
