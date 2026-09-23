"""Project-scoped RAG index for locally stored contract and SOP documents."""

from __future__ import annotations

import hashlib
import gc
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


logger = logging.getLogger(__name__)


def safe_project_id(project_id: str) -> str:
    """Convert a project identifier to a stable local directory component."""
    value = re.sub(r"[^A-Za-z0-9_-]", "_", project_id.strip())
    if not value:
        raise ValueError("项目标识不能为空")
    return value


class ProjectDocumentKnowledgeBase:
    """Build and query a Chroma index that is isolated to one project."""

    def __init__(
        self,
        project_id: str,
        document_records: list[dict[str, object]],
        embeddings: Any,
        base_dir: Path | None = None,
    ) -> None:
        self.project_id = project_id.strip()
        self.safe_project_id = safe_project_id(self.project_id)
        self.document_records = list(document_records)
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.documents_root = self.base_dir / "data" / "project_documents" / self.safe_project_id
        self.chroma_dir = self.base_dir / "chroma_db" / "projects" / self.safe_project_id
        self.signature_path = self.chroma_dir / ".data_signature"
        self.collection_name = f"project_{self.safe_project_id}_knowledge"
        self.embeddings = embeddings
        self.vectorstore: Chroma | None = None
        self._documents: list[Document] | None = None

    def load_data(self, force_rebuild: bool = False) -> None:
        """Open a current index or atomically replace it after a source change."""
        documents = self._build_documents()
        self._documents = documents
        if not documents:
            self.vectorstore = None
            return
        signature = self._source_signature()
        if not force_rebuild and self._index_is_current(signature):
            self.vectorstore = Chroma(
                collection_name=self.collection_name,
                persist_directory=str(self.chroma_dir),
                embedding_function=self.embeddings,
            )
            return

        self.chroma_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(prefix=".project_chroma_rebuild_", dir=self.chroma_dir.parent))
        activation_dir = staging_dir.with_name(f"{staging_dir.name}_ready")
        try:
            temporary_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                collection_name=self.collection_name,
                persist_directory=str(staging_dir),
            )
            # Windows cannot rename an index directory while Chroma's
            # temporary wrapper still owns its SQLite file handles.
            del temporary_store
            gc.collect()
            # Chroma can retain staging-directory handles at process scope on
            # Windows. Activate a copied, unlocked sibling directory instead.
            shutil.copytree(staging_dir, activation_dir)
            self._activate_staged_index(activation_dir, signature)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if activation_dir.exists():
                shutil.rmtree(activation_dir, ignore_errors=True)

    def search(self, query: str, k: int = 4) -> list[Document]:
        """Return only relevant documents belonging to this project."""
        if not query or not query.strip():
            return []
        self._ensure_loaded()
        documents = self._documents or []
        if not documents:
            return []
        if os.getenv("RAG_RETRIEVAL_MODE", "hybrid").lower() == "vector":
            return self._vector_search(query, k)
        return self.hybrid_search(query, k)

    def hybrid_search(self, query: str, k: int = 4) -> list[Document]:
        """Fuse project-local vector and lexical results using RRF."""
        self._ensure_loaded()
        documents = self._documents or []
        if not documents:
            return []
        vector_documents = self._vector_search(query, max(k * 3, 8))
        lexical_documents = self._lexical_search(query, documents, max(k * 3, 8))
        ranked: dict[str, float] = {}
        by_key: dict[str, Document] = {}
        for ranked_documents in (vector_documents, lexical_documents):
            for rank, document in enumerate(ranked_documents, start=1):
                key = self._document_key(document)
                by_key[key] = document
                ranked[key] = ranked.get(key, 0.0) + 1 / (60 + rank)
        return [by_key[key] for key in sorted(ranked, key=ranked.get, reverse=True)[:k]]

    def _vector_search(self, query: str, k: int) -> list[Document]:
        if self.vectorstore is None:
            return []
        try:
            results = self.vectorstore.similarity_search(query.strip(), k=k)
        except Exception:
            logger.exception("Project document vector retrieval failed; using lexical retrieval only.")
            return []
        return [
            document for document in results
            if document.metadata.get("type") == "project_document"
            and document.metadata.get("project_id") == self.project_id
        ]

    def _build_documents(self) -> list[Document]:
        documents: list[Document] = []
        splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "；", "，", " "],
            chunk_size=700,
            chunk_overlap=100,
            length_function=len,
        )
        for record in self.document_records:
            if str(record.get("project_id", "")) != self.project_id or record.get("status", "active") != "active":
                continue
            path = self._safe_document_path(record.get("storage_path"))
            if path is None or not path.exists() or path.suffix.lower() not in {".txt", ".md"}:
                logger.warning("Skipping unavailable project document %s", record.get("id"))
                continue
            content = path.read_bytes()
            expected_hash = str(record.get("content_hash", ""))
            if not expected_hash or hashlib.sha256(content).hexdigest() != expected_hash:
                logger.warning("Skipping project document %s because its hash does not match", record.get("id"))
                continue
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Skipping project document %s because it is not UTF-8", record.get("id"))
                continue
            base_metadata = {
                "type": "project_document",
                "project_id": self.project_id,
                "document_id": str(record.get("id", "")),
                "document_type": str(record.get("document_type", "other")),
                "title": str(record.get("title", "项目资料")),
                "version": str(record.get("version", "未标注版本")),
                "content_hash": expected_hash,
            }
            for chunk_index, chunk in enumerate(splitter.create_documents([text]), start=1):
                chunk.metadata = {**base_metadata, "chunk_index": chunk_index}
                documents.append(chunk)
        return documents

    def _safe_document_path(self, storage_path: object) -> Path | None:
        """Only accept paths under this project's managed document directory."""
        if not isinstance(storage_path, str) or not storage_path:
            return None
        candidate = (self.base_dir / storage_path).resolve()
        expected_root = self.documents_root.resolve()
        try:
            candidate.relative_to(expected_root)
        except ValueError:
            logger.warning("Rejected project document path outside the project directory")
            return None
        return candidate

    def _source_signature(self) -> str:
        digest = hashlib.sha256()
        for record in sorted(self.document_records, key=lambda item: str(item.get("id", ""))):
            digest.update(
                "|".join(
                    str(record.get(field, ""))
                    for field in ("id", "project_id", "title", "content_hash", "document_type", "version", "status")
                ).encode("utf-8")
            )
        return digest.hexdigest()

    def _index_is_current(self, signature: str) -> bool:
        return self.chroma_dir.exists() and self.signature_path.exists() and self.signature_path.read_text(encoding="utf-8") == signature

    def _ensure_loaded(self) -> None:
        if self._documents is None:
            self.load_data()

    def _activate_staged_index(self, staging_dir: Path, signature: str) -> None:
        """Swap a complete staged index in while retaining a recoverable backup."""
        backup_dir = self.chroma_dir.with_name(f"{self.chroma_dir.name}.bak")
        had_current_index = self.chroma_dir.exists()
        if backup_dir.exists() and not had_current_index:
            backup_dir.replace(self.chroma_dir)
            had_current_index = True
        elif backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        active_moved = False
        staging_moved = False
        previous_vectorstore = self.vectorstore
        try:
            if had_current_index:
                self.chroma_dir.replace(backup_dir)
                active_moved = True
            staging_dir.replace(self.chroma_dir)
            staging_moved = True
            self.vectorstore = Chroma(
                collection_name=self.collection_name,
                persist_directory=str(self.chroma_dir),
                embedding_function=self.embeddings,
            )
            self.signature_path.write_text(signature, encoding="utf-8")
        except Exception:
            self.vectorstore = previous_vectorstore
            if staging_moved and self.chroma_dir.exists():
                shutil.rmtree(self.chroma_dir, ignore_errors=True)
            if active_moved and backup_dir.exists():
                backup_dir.replace(self.chroma_dir)
            raise
        else:
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

    @staticmethod
    def _document_key(document: Document) -> str:
        return f"{document.metadata.get('document_id', '')}:{document.metadata.get('chunk_index', '')}"

    @staticmethod
    def _lexical_search(query: str, documents: list[Document], limit: int) -> list[Document]:
        terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", query.lower()))
        if not terms:
            return []
        scored: list[tuple[int, int, Document]] = []
        for index, document in enumerate(documents):
            content_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", document.page_content.lower()))
            score = len(terms & content_terms)
            if score:
                scored.append((score, -index, document))
        scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
        return [document for _, _, document in scored[:limit]]
