"""Tests for project-scoped document retrieval boundaries."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from langchain_core.documents import Document

from project_knowledge_base import ProjectDocumentKnowledgeBase


def document_record(project_id: str, document_id: int, storage_path: str, content: bytes) -> dict[str, object]:
    return {
        "id": document_id,
        "project_id": project_id,
        "title": "入场作业规范",
        "document_type": "sop",
        "version": "v2.1",
        "storage_path": storage_path,
        "content_hash": hashlib.sha256(content).hexdigest(),
        "status": "active",
    }


class ProjectKnowledgeBaseTests(unittest.TestCase):
    def test_builds_chunks_with_required_project_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = "新员工进入车间前必须完成安全培训。\n".encode("utf-8")
            source = root / "data" / "project_documents" / "project-a" / "contract.md"
            source.parent.mkdir(parents=True)
            source.write_bytes(content)
            record = document_record("project-a", 42, "data/project_documents/project-a/contract.md", content)
            knowledge_base = ProjectDocumentKnowledgeBase("project-a", [record], embeddings=Mock(), base_dir=root)

            documents = knowledge_base._build_documents()

            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0].metadata["type"], "project_document")
            self.assertEqual(documents[0].metadata["project_id"], "project-a")
            self.assertEqual(documents[0].metadata["document_id"], "42")
            self.assertEqual(documents[0].metadata["version"], "v2.1")
            self.assertEqual(documents[0].metadata["content_hash"], record["content_hash"])

    def test_search_filters_vector_result_from_other_project(self) -> None:
        knowledge_base = ProjectDocumentKnowledgeBase("project-a", [], embeddings=Mock())
        local = Document(
            page_content="进入车间前必须完成安全培训。",
            metadata={"type": "project_document", "project_id": "project-a", "document_id": "1", "chunk_index": 1},
        )
        foreign = Document(
            page_content="其他项目的合同内容。",
            metadata={"type": "project_document", "project_id": "project-b", "document_id": "2", "chunk_index": 1},
        )
        knowledge_base._documents = [local]
        knowledge_base.vectorstore = Mock()
        knowledge_base.vectorstore.similarity_search.return_value = [foreign, local]

        results = knowledge_base.hybrid_search("安全培训", k=4)

        self.assertEqual(results, [local])
        self.assertTrue(all(result.metadata["project_id"] == "project-a" for result in results))

    def test_rejects_document_path_outside_managed_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            knowledge_base = ProjectDocumentKnowledgeBase("project-a", [], embeddings=Mock(), base_dir=root)
            self.assertIsNone(knowledge_base._safe_document_path("data/project_documents/project-b/other.md"))
            self.assertIsNone(knowledge_base._safe_document_path("../../outside.md"))

    def test_source_signature_changes_when_display_metadata_changes(self) -> None:
        record = document_record("project-a", 42, "data/project_documents/project-a/contract.md", b"test")
        knowledge_base = ProjectDocumentKnowledgeBase("project-a", [record], embeddings=Mock())
        original_signature = knowledge_base._source_signature()
        record["title"] = "更新后的入场规范"
        self.assertNotEqual(original_signature, knowledge_base._source_signature())


if __name__ == "__main__":
    unittest.main()
