"""Tests for project document registration and upload validation."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from conversation_store import ConversationStore
from project_documents import store_text_document


class ProjectDocumentStoreTests(unittest.TestCase):
    def test_registering_same_content_is_idempotent_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "labor_ai.db")
            content_hash = hashlib.sha256(b"# Test contract\nService level: 2 days.").hexdigest()
            first_id = store.register_project_document(
                "demo-project", "测试合同", "contract", "v1.0", "contract.md",
                "data/project_documents/demo-project/test.md", content_hash,
            )
            duplicate_id = store.register_project_document(
                "demo-project", "测试合同副本", "contract", "v2.0", "copy.md",
                "data/project_documents/demo-project/copy.md", content_hash,
            )
            documents = store.list_project_documents()
            self.assertEqual(first_id, duplicate_id)
            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0]["version"], "v1.0")
            self.assertEqual(documents[0]["content_hash"], content_hash)
            self.assertEqual(store.list_audit_events()[0]["object_type"], "project_document")

    def test_upload_rejects_unsupported_or_invalid_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "labor_ai.db")
            arguments = {
                "store": store,
                "project_id": "demo-project",
                "title": "测试资料",
                "document_type": "sop",
                "version": "v1.0",
            }
            with self.assertRaisesRegex(ValueError, "只支持"):
                store_text_document(original_filename="test.pdf", content=b"text", **arguments)
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                store_text_document(original_filename="test.txt", content=b"\xff", **arguments)
            with self.assertRaisesRegex(ValueError, "空白"):
                store_text_document(original_filename="test.md", content=b" \n", **arguments)

    def test_registration_rejects_unknown_project_and_invalid_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "labor_ai.db")
            with self.assertRaisesRegex(ValueError, "项目不存在"):
                store.register_project_document(
                    "unknown-project", "测试资料", "sop", "v1.0", "test.md",
                    "data/project_documents/unknown-project/test.md", "a" * 64,
                )
            with self.assertRaisesRegex(ValueError, "校验值"):
                store.register_project_document(
                    "demo-project", "测试资料", "sop", "v1.0", "test.md",
                    "data/project_documents/demo-project/test.md", "not-a-hash",
                )


if __name__ == "__main__":
    unittest.main()
