"""Regression tests for safe on-disk Chroma index activation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from knowledge_base import KnowledgeBase
from langchain_core.documents import Document


class IndexActivationTests(unittest.TestCase):
    def test_hybrid_search_fuses_lexical_and_vector_rankings(self) -> None:
        knowledge_base = KnowledgeBase.__new__(KnowledgeBase)
        vector_result = Document(page_content="岗位：普工，石岩，6000元", metadata={"type": "job", "job_id": "1", "title": "普工"})
        lexical_result = Document(page_content="岗位：叉车司机，石岩，叉车证", metadata={"type": "job", "job_id": "2", "title": "叉车司机"})
        knowledge_base.vectorstore = Mock()
        knowledge_base.vectorstore.similarity_search.return_value = [vector_result, lexical_result]
        knowledge_base._ensure_loaded = Mock()
        knowledge_base._build_documents = Mock(return_value=[vector_result, lexical_result])

        results = knowledge_base.hybrid_search("石岩 普工", k=2)

        self.assertEqual([document.metadata["job_id"] for document in results], ["1", "2"])

    def test_failed_staging_move_restores_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            knowledge_base = KnowledgeBase.__new__(KnowledgeBase)
            knowledge_base.chroma_dir = root / "chroma_db"
            knowledge_base.signature_path = knowledge_base.chroma_dir / ".data_signature"
            knowledge_base.collection_name = "test_collection"
            knowledge_base.embeddings = Mock()
            knowledge_base.vectorstore = None

            knowledge_base.chroma_dir.mkdir()
            (knowledge_base.chroma_dir / "old-index.txt").write_text("old", encoding="utf-8")
            staging_dir = root / ".chroma_rebuild_test"
            staging_dir.mkdir()
            (staging_dir / "new-index.txt").write_text("new", encoding="utf-8")

            original_replace = Path.replace

            def fail_when_activating(source: Path, target: Path) -> Path:
                if source == staging_dir:
                    raise OSError("simulated staging activation failure")
                return original_replace(source, target)

            with patch.object(Path, "replace", new=fail_when_activating):
                with self.assertRaisesRegex(OSError, "simulated staging activation failure"):
                    knowledge_base._activate_staged_index(staging_dir, "new-signature")

            self.assertTrue(knowledge_base.chroma_dir.exists())
            self.assertEqual(
                (knowledge_base.chroma_dir / "old-index.txt").read_text(encoding="utf-8"),
                "old",
            )
            self.assertFalse((root / "chroma_db.bak").exists())

    def test_failed_backup_move_keeps_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            knowledge_base = KnowledgeBase.__new__(KnowledgeBase)
            knowledge_base.chroma_dir = root / "chroma_db"
            knowledge_base.signature_path = knowledge_base.chroma_dir / ".data_signature"
            knowledge_base.collection_name = "test_collection"
            knowledge_base.embeddings = Mock()
            knowledge_base.vectorstore = None

            knowledge_base.chroma_dir.mkdir()
            (knowledge_base.chroma_dir / "old-index.txt").write_text("old", encoding="utf-8")
            staging_dir = root / ".chroma_rebuild_test"
            staging_dir.mkdir()

            original_replace = Path.replace

            def fail_when_backing_up(source: Path, target: Path) -> Path:
                if source == knowledge_base.chroma_dir:
                    raise OSError("simulated backup failure")
                return original_replace(source, target)

            with patch.object(Path, "replace", new=fail_when_backing_up):
                with self.assertRaisesRegex(OSError, "simulated backup failure"):
                    knowledge_base._activate_staged_index(staging_dir, "new-signature")

            self.assertTrue(knowledge_base.chroma_dir.exists())
            self.assertEqual(
                (knowledge_base.chroma_dir / "old-index.txt").read_text(encoding="utf-8"),
                "old",
            )

    def test_failed_staging_move_restores_stale_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            knowledge_base = KnowledgeBase.__new__(KnowledgeBase)
            knowledge_base.chroma_dir = root / "chroma_db"
            knowledge_base.signature_path = knowledge_base.chroma_dir / ".data_signature"
            knowledge_base.collection_name = "test_collection"
            knowledge_base.embeddings = Mock()
            knowledge_base.vectorstore = None

            backup_dir = root / "chroma_db.bak"
            backup_dir.mkdir()
            (backup_dir / "old-index.txt").write_text("old", encoding="utf-8")
            staging_dir = root / ".chroma_rebuild_test"
            staging_dir.mkdir()

            original_replace = Path.replace

            def fail_when_activating(source: Path, target: Path) -> Path:
                if source == staging_dir:
                    raise OSError("simulated staging activation failure")
                return original_replace(source, target)

            with patch.object(Path, "replace", new=fail_when_activating):
                with self.assertRaisesRegex(OSError, "simulated staging activation failure"):
                    knowledge_base._activate_staged_index(staging_dir, "new-signature")

            self.assertTrue(knowledge_base.chroma_dir.exists())
            self.assertEqual(
                (knowledge_base.chroma_dir / "old-index.txt").read_text(encoding="utf-8"),
                "old",
            )
            self.assertFalse(backup_dir.exists())

    def test_signature_failure_keeps_previous_vectorstore_and_restores_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            knowledge_base = KnowledgeBase.__new__(KnowledgeBase)
            knowledge_base.chroma_dir = root / "chroma_db"
            knowledge_base.signature_path = knowledge_base.chroma_dir / ".data_signature"
            knowledge_base.collection_name = "test_collection"
            knowledge_base.embeddings = Mock()
            previous_vectorstore = Mock()
            knowledge_base.vectorstore = previous_vectorstore

            knowledge_base.chroma_dir.mkdir()
            (knowledge_base.chroma_dir / "old-index.txt").write_text("old", encoding="utf-8")
            staging_dir = root / ".chroma_rebuild_test"
            staging_dir.mkdir()
            (staging_dir / "new-index.txt").write_text("new", encoding="utf-8")

            original_write_text = Path.write_text

            def fail_when_writing_signature(path: Path, data: str, *args: object, **kwargs: object) -> int:
                if path == knowledge_base.signature_path:
                    raise OSError("simulated signature failure")
                return original_write_text(path, data, *args, **kwargs)

            with patch("knowledge_base.Chroma", return_value=Mock()):
                with patch.object(Path, "write_text", new=fail_when_writing_signature):
                    with self.assertRaisesRegex(OSError, "simulated signature failure"):
                        knowledge_base._activate_staged_index(staging_dir, "new-signature")

            self.assertIs(knowledge_base.vectorstore, previous_vectorstore)
            self.assertEqual(
                (knowledge_base.chroma_dir / "old-index.txt").read_text(encoding="utf-8"),
                "old",
            )
            self.assertFalse((root / "chroma_db.bak").exists())


if __name__ == "__main__":
    unittest.main()
