"""Small SQLite store for local-only chat audit records."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ConversationStore:
    """Persist messages locally so demo conversations can be reviewed after a session."""

    def __init__(self, database_path: Path | None = None) -> None:
        root = Path(__file__).resolve().parent
        self.database_path = database_path or root / "data" / "labor_ai.db"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_message(self, session_id: str, role: str, content: str, sources: list[str] | None = None) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, sources_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, json.dumps(sources or [], ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )

    def message_count(self) -> int:
        with sqlite3.connect(self.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])

    def _initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            # WAL 模式支持并发读写；busy_timeout 避免 "database is locked"
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
