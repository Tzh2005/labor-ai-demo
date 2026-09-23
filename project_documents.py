"""Local storage helpers for project-scoped text knowledge documents."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from conversation_store import ConversationStore


_ALLOWED_SUFFIXES = {".md", ".txt"}
_MAX_DOCUMENT_BYTES = 512 * 1024


def store_text_document(
    store: ConversationStore,
    project_id: str,
    title: str,
    document_type: str,
    version: str,
    original_filename: str,
    content: bytes,
    actor_id: str = "local_user",
) -> int:
    """Validate and persist a UTF-8 text document under its project directory."""
    filename = Path(original_filename).name
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError("当前只支持 .txt 和 .md 文档")
    if not content or len(content) > _MAX_DOCUMENT_BYTES:
        raise ValueError("文档必须非空且不超过 512KB")
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("文档必须使用 UTF-8 编码") from error
    if not decoded.strip():
        raise ValueError("文档不能只包含空白内容")
    digest = hashlib.sha256(content).hexdigest()
    safe_project = re.sub(r"[^A-Za-z0-9_-]", "_", project_id)
    root = Path(__file__).resolve().parent / "data" / "project_documents" / safe_project
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{digest}{suffix}"
    if not target.exists():
        target.write_bytes(content)
    relative_path = target.relative_to(Path(__file__).resolve().parent).as_posix()
    return store.register_project_document(
        project_id=project_id,
        title=title,
        document_type=document_type,
        version=version,
        original_filename=filename,
        storage_path=relative_path,
        content_hash=digest,
        actor_id=actor_id,
    )
