"""Local RAG knowledge base for jobs and FAQ data."""

from __future__ import annotations

import hashlib
import gc
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


logger = logging.getLogger(__name__)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def load_jobs_file(jobs_path: Path) -> list[dict[str, object]]:
    """Read and validate the JSON job list without initializing ML dependencies."""
    if not jobs_path.exists():
        return []
    with jobs_path.open("r", encoding="utf-8") as file:
        jobs = json.load(file)
    if not isinstance(jobs, list):
        raise ValueError("data/jobs.json must contain a JSON array.")
    return jobs


class KnowledgeBase:
    """Build and query the on-disk Chroma index used by the assistant."""

    collection_name = "labor_ai_knowledge"

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5") -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.data_dir = self.base_dir / "data"
        self.jobs_path = self.data_dir / "jobs.json"
        self.faq_path = self.data_dir / "faq.md"
        self.chroma_dir = self.base_dir / "chroma_db"
        self.signature_path = self.chroma_dir / ".data_signature"
        self.model_name = model_name
        self.vectorstore: Chroma | None = None
        self.embeddings = self._load_embeddings(model_name)

    @staticmethod
    def _load_embeddings(model_name: str) -> HuggingFaceEmbeddings:
        """Load the embedding model from the local cache first to avoid HuggingFace network checks."""
        encode_kwargs = {"normalize_embeddings": True}
        try:
            return HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu", "local_files_only": True},
                encode_kwargs=encode_kwargs,
            )
        except Exception:
            return HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs=encode_kwargs,
            )

    def load_data(self, force_rebuild: bool = False) -> None:
        """Load a current index, rebuilding only when source data changed.

        Rebuild uses a temporary directory first and atomically swaps it in,
        so a failed rebuild (e.g. OOM) leaves the existing index intact.
        """
        documents = self._build_documents()
        signature = self._source_signature()
        if not force_rebuild and self._index_is_current(signature):
            self.vectorstore = Chroma(
                collection_name=self.collection_name,
                persist_directory=str(self.chroma_dir),
                embedding_function=self.embeddings,
            )
            return

        # Build on the target volume so a directory rename is atomic. A system
        # temp directory can be on a different drive on Windows, where moving
        # it becomes a copy and can leave no usable index after an interruption.
        staging_dir = Path(tempfile.mkdtemp(prefix=".chroma_rebuild_", dir=self.chroma_dir.parent))
        activation_dir = staging_dir.with_name(f"{staging_dir.name}_ready")
        try:
            tmp_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                collection_name=self.collection_name,
                persist_directory=str(staging_dir),
            )
            # Chroma keeps SQLite handles on Windows until the temporary
            # wrapper is collected; release them before renaming the folder.
            del tmp_store
            gc.collect()
            # Chroma's process-level client can retain the staging directory
            # on Windows. Copying to an untouched sibling keeps the staged
            # contents intact while giving the atomic activation step a free
            # directory handle to rename.
            shutil.copytree(staging_dir, activation_dir)
            self._activate_staged_index(activation_dir, signature)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if activation_dir.exists():
                shutil.rmtree(activation_dir, ignore_errors=True)
        logger.info("Chroma index rebuilt and swapped in (signature=%s)", signature[:12])

    def _activate_staged_index(self, staging_dir: Path, signature: str) -> None:
        """Replace the active index with a same-volume staging directory.

        The previous index remains recoverable until the staged directory has
        been moved into place, opened by Chroma, and received its data signature.
        """
        backup_dir = self.chroma_dir.with_name(f"{self.chroma_dir.name}.bak")
        had_current_index = self.chroma_dir.exists()
        if backup_dir.exists() and not had_current_index:
            # A previous process may have stopped after moving the active
            # directory aside. Restore that only copy before trying again.
            backup_dir.replace(self.chroma_dir)
            had_current_index = True
        elif backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        active_moved = False
        staging_moved = False
        try:
            if had_current_index:
                self.chroma_dir.replace(backup_dir)
                active_moved = True
            staging_dir.replace(self.chroma_dir)
            staging_moved = True
            new_vectorstore = Chroma(
                collection_name=self.collection_name,
                persist_directory=str(self.chroma_dir),
                embedding_function=self.embeddings,
            )
            self.signature_path.write_text(signature, encoding="utf-8")
            self.vectorstore = new_vectorstore
        except Exception:
            # A new directory may already be active if validation failed after
            # the rename. Remove it before putting the known-good backup back.
            if staging_moved and self.chroma_dir.exists():
                shutil.rmtree(self.chroma_dir, ignore_errors=True)
            if active_moved and backup_dir.exists():
                backup_dir.replace(self.chroma_dir)
            raise
        else:
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

    def search(self, query: str, k: int = 4) -> list[Document]:
        """Return the most relevant job and FAQ documents for a question."""
        if not query or not query.strip():
            return []
        self._ensure_loaded()
        if os.getenv("RAG_RETRIEVAL_MODE", "hybrid").lower() == "vector":
            return self.vectorstore.similarity_search(query.strip(), k=k)
        return self.hybrid_search(query, k=k)

    def hybrid_search(self, query: str, k: int = 4, document_type: str | None = None) -> list[Document]:
        """Fuse vector and lexical rankings with Reciprocal Rank Fusion (RRF)."""
        if not query or not query.strip():
            return []
        self._ensure_loaded()
        documents = self._build_documents()
        if document_type:
            documents = [document for document in documents if document.metadata.get("type") == document_type]
        if not documents:
            return []

        vector_documents: list[Document] = []
        try:
            vector_documents = self.vectorstore.similarity_search(query.strip(), k=max(k * 3, 8))
            if document_type:
                vector_documents = [document for document in vector_documents if document.metadata.get("type") == document_type]
        except Exception:
            logger.exception("Vector retrieval failed; using lexical retrieval only.")

        lexical_documents = self._lexical_search(query, documents, max(k * 3, 8))
        ranked: dict[str, float] = {}
        by_key: dict[str, Document] = {}
        for ranked_documents in (vector_documents, lexical_documents):
            for rank, document in enumerate(ranked_documents, start=1):
                key = self._document_key(document)
                by_key[key] = document
                ranked[key] = ranked.get(key, 0.0) + 1 / (60 + rank)
        return [by_key[key] for key in sorted(ranked, key=ranked.get, reverse=True)[:k]]

    @staticmethod
    def _document_key(document: Document) -> str:
        stable = document.metadata.get("job_id") or document.metadata.get("title") or document.page_content
        return f"{document.metadata.get('type', 'document')}:{stable}"

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

    def search_jobs(self, query: str, k: int = 5) -> list[Document]:
        """Return only job documents for recommendations and job browsing."""
        if not query or not query.strip():
            return []
        self._ensure_loaded()
        if os.getenv("RAG_RETRIEVAL_MODE", "hybrid").lower() == "vector":
            return self.vectorstore.similarity_search(query.strip(), k=k, filter={"type": "job"})
        return self.hybrid_search(query, k=k, document_type="job")

    def stats(self) -> dict[str, int | bool]:
        """Return lightweight status without loading the embedding model."""
        jobs = self.load_jobs()
        faq_sections = self.faq_path.read_text(encoding="utf-8").count("### Q:") if self.faq_path.exists() else 0
        return {"jobs": len(jobs), "faq_sections": faq_sections, "index_current": self._index_is_current(self._source_signature())}

    def load_jobs(self) -> list[dict[str, object]]:
        """Read raw jobs for the browser view without invoking vector search."""
        return load_jobs_file(self.jobs_path)

    def _ensure_loaded(self) -> None:
        if self.vectorstore is None:
            self.load_data()

    def _build_documents(self) -> list[Document]:
        documents: list[Document] = []
        required = ("id", "factory_name", "position", "salary", "requirements", "benefits", "work_time", "location", "overtime")
        for job in self.load_jobs():
            missing = [field for field in required if field not in job]
            if missing:
                raise ValueError(f"Job {job.get('id', 'unknown')} is missing fields: {', '.join(missing)}")
            content = (
                "[岗位信息]\n"
                f"工厂：{job['factory_name']}\n职位：{job['position']}\n工资：{job['salary']}\n"
                f"要求：{job['requirements']}\n福利：{job['benefits']}\n工作时间：{job['work_time']}\n"
                f"工作地点：{job['location']}\n加班情况：{job['overtime']}"
            )
            documents.append(Document(
                page_content=content,
                metadata={"type": "job", "job_id": str(job["id"]), "title": f"{job['factory_name']} - {job['position']}", "location": str(job["location"])},
            ))

        if self.faq_path.exists():
            splitter = RecursiveCharacterTextSplitter(separators=["\n### Q:", "\n---", "\n\n"], chunk_size=550, chunk_overlap=60, length_function=len)
            for index, document in enumerate(splitter.create_documents([self.faq_path.read_text(encoding="utf-8")]), start=1):
                document.metadata = {"type": "faq", "title": f"常见问题 {index}"}
                documents.append(document)
        if not documents:
            raise FileNotFoundError("No job or FAQ documents found under the data directory.")
        return documents

    def _source_signature(self) -> str:
        digest = hashlib.sha256()
        for path in (self.jobs_path, self.faq_path):
            digest.update(path.name.encode("utf-8"))
            if path.exists():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def _index_is_current(self, signature: str) -> bool:
        return self.chroma_dir.exists() and self.signature_path.exists() and self.signature_path.read_text(encoding="utf-8") == signature


if __name__ == "__main__":
    knowledge_base = KnowledgeBase()
    knowledge_base.load_data()
    print(knowledge_base.stats())
    for result in knowledge_base.search_jobs("石岩 普工", k=3):
        print(result.metadata["title"])
