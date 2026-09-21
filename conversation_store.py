"""SQLite persistence for chat audit records and structured job data."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConversationStore:
    """Persist messages locally so demo conversations can be reviewed after a session."""

    def __init__(self, database_path: Path | None = None) -> None:
        root = Path(__file__).resolve().parent
        self.database_path = database_path or root / "data" / "labor_ai.db"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_message(self, session_id: str, role: str, content: str, sources: list[str] | None = None) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_messages (session_id, role, content, sources_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, role, content, json.dumps(sources or [], ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
                )

    def sync_jobs_from_file(self, jobs_path: Path) -> int:
        """Import the JSON job snapshot into SQLite and return its row count.

        JSON remains the migration source of truth for this first step. The
        operation is idempotent, so it is safe to run on every app startup.
        """
        with jobs_path.open("r", encoding="utf-8") as file:
            jobs = json.load(file)
        if not isinstance(jobs, list):
            raise ValueError("jobs source must contain a JSON array")

        required = (
            "id", "factory_name", "position", "salary", "requirements",
            "benefits", "work_time", "location", "overtime",
        )
        normalized: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                raise ValueError("each job must be a JSON object")
            missing = [field for field in required if field not in job]
            if missing:
                raise ValueError(f"job {job.get('id', 'unknown')} is missing: {', '.join(missing)}")
            normalized.append({field: job[field] for field in required})

        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO jobs (
                        id, factory_name, position, salary, requirements,
                        benefits, work_time, location, overtime, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        factory_name=excluded.factory_name,
                        position=excluded.position,
                        salary=excluded.salary,
                        requirements=excluded.requirements,
                        benefits=excluded.benefits,
                        work_time=excluded.work_time,
                        location=excluded.location,
                        overtime=excluded.overtime,
                        updated_at=excluded.updated_at
                    """,
                    [
                        (
                            int(job["id"]),
                            *(str(job[field]) for field in required[1:]),
                            datetime.now(timezone.utc).isoformat(),
                        )
                        for job in normalized
                    ],
                )
                source_ids = [int(job["id"]) for job in normalized]
                if source_ids:
                    placeholders = ",".join("?" for _ in source_ids)
                    connection.execute(f"DELETE FROM jobs WHERE id NOT IN ({placeholders})", source_ids)
                else:
                    connection.execute("DELETE FROM jobs")
        return len(normalized)

    def list_jobs(self, location: str | None = None, position: str | None = None) -> list[dict[str, Any]]:
        """Return jobs using the same field shape as the legacy JSON loader."""
        clauses: list[str] = []
        values: list[str] = []
        if location:
            clauses.append("location LIKE ?")
            values.append(f"%{location}%")
        if position:
            clauses.append("position = ?")
            values.append(position)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    f"SELECT id, factory_name, position, salary, requirements, benefits, work_time, location, overtime FROM jobs {where} ORDER BY id",
                    values,
                ).fetchall()
        return [dict(row) for row in rows]

    def job_count(self) -> int:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                return int(connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    def create_candidate(
        self,
        name: str,
        phone: str,
        age: int | None,
        gender: str,
        preferred_location: str,
        preferred_position: str,
        skills: str,
    ) -> int:
        """Create a candidate while keeping the phone number out of plaintext storage."""
        clean_phone = "".join(character for character in phone if character.isdigit())
        if len(clean_phone) < 7:
            raise ValueError("手机号至少需要 7 位数字")
        if not name.strip():
            raise ValueError("候选人姓名不能为空")
        phone_hash = hashlib.sha256(clean_phone.encode("utf-8")).hexdigest()
        phone_last4 = clean_phone[-4:]
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO candidates (
                        name, phone_hash, phone_last4, age, gender,
                        preferred_location, preferred_position, skills, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                    """,
                    (name.strip(), phone_hash, phone_last4, age, gender.strip(), preferred_location.strip(), preferred_position.strip(), skills.strip(), now),
                )
                return int(cursor.lastrowid)

    def list_candidates(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT id, name, phone_last4, age, gender, preferred_location,
                           preferred_position, skills, status, created_at
                    FROM candidates ORDER BY id DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]

    def create_application(self, candidate_id: int, job_id: int) -> int:
        """Create an application once; repeated clicks return the existing row."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO applications (candidate_id, job_id, status, created_at, updated_at)
                    VALUES (?, ?, 'applied', ?, ?)
                    ON CONFLICT(candidate_id, job_id) DO NOTHING
                    """,
                    (candidate_id, job_id, now, now),
                )
                row = connection.execute(
                    "SELECT id FROM applications WHERE candidate_id = ? AND job_id = ?",
                    (candidate_id, job_id),
                ).fetchone()
        if row is None:
            raise RuntimeError("报名记录创建失败")
        return int(row[0])

    def list_applications(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT applications.id, applications.candidate_id, candidates.name,
                           applications.job_id, jobs.factory_name, jobs.position,
                           applications.status, applications.created_at
                    FROM applications
                    JOIN candidates ON candidates.id = applications.candidate_id
                    JOIN jobs ON jobs.id = applications.job_id
                    ORDER BY applications.id DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]

    def update_application_status(self, application_id: int, status: str) -> None:
        allowed = {"applied", "interview", "hired", "rejected", "withdrawn"}
        if status not in allowed:
            raise ValueError(f"不支持的报名状态: {status}")
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    "UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
                    (status, datetime.now(timezone.utc).isoformat(), application_id),
                )

    def message_count(self) -> int:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                return int(connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])

    def _initialize(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
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
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS candidates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        phone_hash TEXT NOT NULL,
                        phone_last4 TEXT NOT NULL,
                        age INTEGER,
                        gender TEXT NOT NULL,
                        preferred_location TEXT NOT NULL,
                        preferred_position TEXT NOT NULL,
                        skills TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('new', 'contacted', 'active', 'inactive')),
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS applications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        candidate_id INTEGER NOT NULL REFERENCES candidates(id),
                        job_id INTEGER NOT NULL REFERENCES jobs(id),
                        status TEXT NOT NULL CHECK (status IN ('applied', 'interview', 'hired', 'rejected', 'withdrawn')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(candidate_id, job_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id INTEGER PRIMARY KEY,
                        factory_name TEXT NOT NULL,
                        position TEXT NOT NULL,
                        salary TEXT NOT NULL,
                        requirements TEXT NOT NULL,
                        benefits TEXT NOT NULL,
                        work_time TEXT NOT NULL,
                        location TEXT NOT NULL,
                        overtime TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
