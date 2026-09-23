"""Tests for synthetic demo data seeding."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conversation_store import ConversationStore
from demo_seed import seed_demo_data


class DemoSeedTests(unittest.TestCase):
    def test_seed_is_synthetic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "labor_ai.db")
            first = seed_demo_data(store)
            second = seed_demo_data(store)
            self.assertEqual(first, second)
            self.assertEqual(first["candidates"], 5)
            self.assertEqual(first["applications"], 5)
            self.assertEqual(first["workers"], 3)
            self.assertTrue(all(item["name"].startswith("测试工人·") for item in store.list_candidates()))


if __name__ == "__main__":
    unittest.main()
