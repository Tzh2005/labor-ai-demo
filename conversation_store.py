"""SQLite persistence for project delivery data and audit evidence."""

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

    DEFAULT_PROJECT_ID = "demo-project"

    def ensure_default_project(self) -> dict[str, Any]:
        """Return the local demo project used until real tenant auth is added."""
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT id, name, client_name, status FROM projects WHERE id = ?",
                    (self.DEFAULT_PROJECT_ID,),
                ).fetchone()
        return dict(row) if row else {
            "id": self.DEFAULT_PROJECT_ID,
            "name": "全通劳务演示项目",
            "client_name": "演示甲方",
            "status": "active",
        }

    def list_projects(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT id, name, client_name, status, created_at FROM projects ORDER BY created_at"
                ).fetchall()
        return [dict(row) for row in rows]

    def record_audit_event(
        self,
        action: str,
        object_type: str,
        object_id: str | int,
        details: dict[str, Any] | None = None,
        project_id: str = DEFAULT_PROJECT_ID,
        actor_id: str = "local_user",
    ) -> int:
        """Append an integrity-chained audit event without storing secrets."""
        created_at = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                previous = connection.execute(
                    "SELECT event_hash FROM audit_events WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
                previous_hash = previous[0] if previous else ""
                payload = "|".join((project_id, actor_id, action, object_type, str(object_id), details_json, created_at, previous_hash))
                event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                cursor = connection.execute(
                    """
                    INSERT INTO audit_events (
                        project_id, actor_id, action, object_type, object_id,
                        details_json, created_at, previous_hash, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, actor_id, action, object_type, str(object_id), details_json, created_at, previous_hash, event_hash),
                )
                return int(cursor.lastrowid)

    def list_audit_events(self, project_id: str = DEFAULT_PROJECT_ID, limit: int = 50) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT id, project_id, actor_id, action, object_type, object_id,
                           details_json, created_at, previous_hash, event_hash
                    FROM audit_events WHERE project_id = ? ORDER BY id DESC LIMIT ?
                    """,
                    (project_id, max(1, min(limit, 200))),
                ).fetchall()
        return [dict(row) for row in rows]

    def dashboard_metrics(self, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, int | float]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                jobs = connection.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ?", (project_id,)).fetchone()[0]
                candidates = connection.execute("SELECT COUNT(*) FROM candidates WHERE project_id = ?", (project_id,)).fetchone()[0]
                applications = connection.execute("SELECT COUNT(*) FROM applications WHERE project_id = ?", (project_id,)).fetchone()[0]
                hired = connection.execute("SELECT COUNT(*) FROM applications WHERE project_id = ? AND status = 'hired'", (project_id,)).fetchone()[0]
                interview = connection.execute("SELECT COUNT(*) FROM applications WHERE project_id = ? AND status = 'interview'", (project_id,)).fetchone()[0]
                active = connection.execute("SELECT COUNT(*) FROM applications WHERE project_id = ? AND status IN ('applied', 'interview')", (project_id,)).fetchone()[0]
        return {
            "jobs": int(jobs),
            "candidates": int(candidates),
            "applications": int(applications),
            "active_applications": int(active),
            "interview": int(interview),
            "hired": int(hired),
            "conversion_rate": round((int(hired) / int(applications) * 100), 1) if applications else 0.0,
        }

    def save_message(self, session_id: str, role: str, content: str, sources: list[str] | None = None, project_id: str = DEFAULT_PROJECT_ID) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_messages (project_id, session_id, role, content, sources_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, session_id, role, content, json.dumps(sources or [], ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
                )

    def sync_jobs_from_file(self, jobs_path: Path, project_id: str = DEFAULT_PROJECT_ID) -> int:
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
                        id, project_id, factory_name, position, salary, requirements,
                        benefits, work_time, location, overtime, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        factory_name=excluded.factory_name,
                        position=excluded.position,
                        salary=excluded.salary,
                        requirements=excluded.requirements,
                        benefits=excluded.benefits,
                        work_time=excluded.work_time,
                        location=excluded.location,
                        overtime=excluded.overtime,
                        project_id=excluded.project_id,
                        updated_at=excluded.updated_at
                    """,
                    [
                        (
                            int(job["id"]), project_id,
                            *(str(job[field]) for field in required[1:]),
                            datetime.now(timezone.utc).isoformat(),
                        )
                        for job in normalized
                    ],
                )
                source_ids = [int(job["id"]) for job in normalized]
                if source_ids:
                    placeholders = ",".join("?" for _ in source_ids)
                    connection.execute(f"DELETE FROM jobs WHERE project_id = ? AND id NOT IN ({placeholders})", [project_id, *source_ids])
                else:
                    connection.execute("DELETE FROM jobs WHERE project_id = ?", (project_id,))
        self.record_audit_event("sync", "jobs", project_id, {"count": len(normalized)}, project_id=project_id)
        return len(normalized)

    def list_jobs(self, location: str | None = None, position: str | None = None, project_id: str = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        """Return jobs using the same field shape as the legacy JSON loader."""
        clauses: list[str] = []
        values: list[str] = [project_id]
        clauses.append("project_id = ?")
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

    def job_count(self, project_id: str = DEFAULT_PROJECT_ID) -> int:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                return int(connection.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ?", (project_id,)).fetchone()[0])

    def create_candidate(
        self,
        name: str,
        phone: str,
        age: int | None,
        gender: str,
        preferred_location: str,
        preferred_position: str,
        skills: str,
        project_id: str = DEFAULT_PROJECT_ID,
        actor_id: str = "local_user",
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
                        project_id, name, phone_hash, phone_last4, age, gender,
                        preferred_location, preferred_position, skills, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                    """,
                    (project_id, name.strip(), phone_hash, phone_last4, age, gender.strip(), preferred_location.strip(), preferred_position.strip(), skills.strip(), now),
                )
                candidate_id = int(cursor.lastrowid)
        self.record_audit_event("create", "candidate", candidate_id, {"name": name.strip(), "phone_last4": phone_last4}, project_id, actor_id)
        return candidate_id

    def list_candidates(self, project_id: str = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT id, name, phone_last4, age, gender, preferred_location,
                           preferred_position, skills, status, created_at
                    FROM candidates WHERE project_id = ? ORDER BY id DESC
                    """, (project_id,)
                ).fetchall()
        return [dict(row) for row in rows]

    def create_application(self, candidate_id: int, job_id: int, project_id: str = DEFAULT_PROJECT_ID, actor_id: str = "local_user") -> int:
        """Create an application once; repeated clicks return the existing row."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO applications (project_id, candidate_id, job_id, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'applied', ?, ?)
                    ON CONFLICT(candidate_id, job_id) DO NOTHING
                    """,
                    (project_id, candidate_id, job_id, now, now),
                )
                row = connection.execute(
                    "SELECT id FROM applications WHERE candidate_id = ? AND job_id = ?",
                    (candidate_id, job_id),
                ).fetchone()
        if row is None:
            raise RuntimeError("报名记录创建失败")
        application_id = int(row[0])
        self.record_audit_event("create", "application", application_id, {"candidate_id": candidate_id, "job_id": job_id, "status": "applied"}, project_id, actor_id)
        return application_id

    def list_applications(self, project_id: str = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT applications.id, applications.candidate_id, candidates.name,
                           applications.job_id, jobs.factory_name, jobs.position,
                           applications.status, applications.created_at, applications.updated_at
                    FROM applications
                    JOIN candidates ON candidates.id = applications.candidate_id
                    JOIN jobs ON jobs.id = applications.job_id
                    WHERE applications.project_id = ?
                    ORDER BY applications.id DESC
                    """, (project_id,)
                ).fetchall()
        return [dict(row) for row in rows]

    def update_application_status(self, application_id: int, status: str, project_id: str = DEFAULT_PROJECT_ID, actor_id: str = "local_user") -> None:
        allowed = {"applied", "interview", "hired", "rejected", "withdrawn"}
        if status not in allowed:
            raise ValueError(f"不支持的报名状态: {status}")
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    "UPDATE applications SET status = ?, updated_at = ? WHERE id = ? AND project_id = ?",
                    (status, datetime.now(timezone.utc).isoformat(), application_id, project_id),
                )
        self.record_audit_event("status_change", "application", application_id, {"status": status}, project_id, actor_id)

    def promote_candidate_to_worker(
        self,
        candidate_id: int,
        project_id: str = DEFAULT_PROJECT_ID,
        source_channel: str = "local_registration",
        actor_id: str = "local_user",
    ) -> int:
        """Create the durable worker master record without copying sensitive fields."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                row = connection.execute(
                    "SELECT id FROM workers WHERE project_id = ? AND candidate_id = ?",
                    (project_id, candidate_id),
                ).fetchone()
                if row:
                    return int(row[0])
                cursor = connection.execute(
                    """
                    INSERT INTO workers (project_id, candidate_id, source_channel, lifecycle_status, created_at, updated_at)
                    VALUES (?, ?, ?, 'available', ?, ?)
                    """,
                    (project_id, candidate_id, source_channel, now, now),
                )
                worker_id = int(cursor.lastrowid)
        self.record_audit_event("promote", "worker", worker_id, {"candidate_id": candidate_id, "source_channel": source_channel}, project_id, actor_id)
        return worker_id

    def list_workers(self, project_id: str = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT workers.id, workers.candidate_id, candidates.name, candidates.phone_last4,
                           candidates.preferred_position, workers.source_channel,
                           workers.lifecycle_status, workers.created_at, workers.updated_at
                    FROM workers JOIN candidates ON candidates.id = workers.candidate_id
                    WHERE workers.project_id = ? ORDER BY workers.id DESC
                    """,
                    (project_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def create_placement(
        self,
        worker_id: int,
        job_id: int,
        project_id: str = DEFAULT_PROJECT_ID,
        requested_at: str | None = None,
        actor_id: str = "local_user",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        requested_at = requested_at or now
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO placements (
                        project_id, worker_id, job_id, status, requested_at, created_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                    """,
                    (project_id, worker_id, job_id, requested_at, now, now),
                )
                placement_id = int(cursor.lastrowid)
        self.record_audit_event("create", "placement", placement_id, {"worker_id": worker_id, "job_id": job_id, "status": "pending"}, project_id, actor_id)
        return placement_id

    def list_placements(self, project_id: str = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT placements.id, placements.worker_id, candidates.name,
                           placements.job_id, jobs.factory_name, jobs.position,
                           placements.status, placements.requested_at, placements.onboarded_at,
                           placements.separated_at, placements.separation_reason, placements.updated_at
                    FROM placements
                    JOIN workers ON workers.id = placements.worker_id
                    JOIN candidates ON candidates.id = workers.candidate_id
                    JOIN jobs ON jobs.id = placements.job_id
                    WHERE placements.project_id = ? ORDER BY placements.id DESC
                    """,
                    (project_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def update_placement_status(
        self,
        placement_id: int,
        status: str,
        separation_reason: str = "",
        project_id: str = DEFAULT_PROJECT_ID,
        actor_id: str = "local_user",
    ) -> None:
        allowed = {"pending", "onboarded", "separated", "cancelled"}
        if status not in allowed:
            raise ValueError(f"不支持的派工状态: {status}")
        now = datetime.now(timezone.utc).isoformat()
        onboarded_at = now if status == "onboarded" else None
        separated_at = now if status == "separated" else None
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE placements
                    SET status = ?, onboarded_at = COALESCE(?, onboarded_at),
                        separated_at = COALESCE(?, separated_at), separation_reason = ?, updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (status, onboarded_at, separated_at, separation_reason.strip(), now, placement_id, project_id),
                )
                if status == "onboarded":
                    connection.execute(
                        "UPDATE workers SET lifecycle_status = 'onboarded', updated_at = ? WHERE id = (SELECT worker_id FROM placements WHERE id = ?)",
                        (now, placement_id),
                    )
                elif status == "separated":
                    connection.execute(
                        "UPDATE workers SET lifecycle_status = 'separated', updated_at = ? WHERE id = (SELECT worker_id FROM placements WHERE id = ?)",
                        (now, placement_id),
                    )
        self.record_audit_event("status_change", "placement", placement_id, {"status": status, "separation_reason": separation_reason.strip()}, project_id, actor_id)

    def save_attendance_snapshot(self, snapshot_date: str, on_duty_count: int, source: str = "manual", project_id: str = DEFAULT_PROJECT_ID, actor_id: str = "local_user") -> None:
        if on_duty_count < 0:
            raise ValueError("在岗人数不能为负数")
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO attendance_snapshots (project_id, snapshot_date, on_duty_count, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, snapshot_date) DO UPDATE SET on_duty_count = excluded.on_duty_count, source = excluded.source
                    """,
                    (project_id, snapshot_date, on_duty_count, source.strip(), now),
                )
        self.record_audit_event("snapshot", "attendance", snapshot_date, {"on_duty_count": on_duty_count, "source": source}, project_id, actor_id)

    def list_attendance_snapshots(self, project_id: str = DEFAULT_PROJECT_ID, limit: int = 30) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT snapshot_date, on_duty_count, source, created_at FROM attendance_snapshots WHERE project_id = ? ORDER BY snapshot_date DESC LIMIT ?",
                    (project_id, max(1, min(limit, 365))),
                ).fetchall()
        return [dict(row) for row in rows]

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
                    CREATE TABLE IF NOT EXISTS projects (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        client_name TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL DEFAULT 'demo-project',
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
                        project_id TEXT NOT NULL DEFAULT 'demo-project',
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
                        project_id TEXT NOT NULL DEFAULT 'demo-project',
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
                        project_id TEXT NOT NULL DEFAULT 'demo-project',
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
                # Backward-compatible migration for the existing local demo database.
                self._ensure_column(connection, "chat_messages", "project_id TEXT NOT NULL DEFAULT 'demo-project'")
                self._ensure_column(connection, "candidates", "project_id TEXT NOT NULL DEFAULT 'demo-project'")
                self._ensure_column(connection, "applications", "project_id TEXT NOT NULL DEFAULT 'demo-project'")
                self._ensure_column(connection, "jobs", "project_id TEXT NOT NULL DEFAULT 'demo-project'")
                now = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    """
                    INSERT INTO projects (id, name, client_name, status, created_at)
                    VALUES (?, ?, ?, 'active', ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (self.DEFAULT_PROJECT_ID, "全通劳务演示项目", "演示甲方", now),
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL REFERENCES projects(id),
                        candidate_id INTEGER NOT NULL REFERENCES candidates(id),
                        source_channel TEXT NOT NULL,
                        lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('available', 'onboarded', 'separated', 'inactive')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(project_id, candidate_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS placements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL REFERENCES projects(id),
                        worker_id INTEGER NOT NULL REFERENCES workers(id),
                        job_id INTEGER NOT NULL REFERENCES jobs(id),
                        status TEXT NOT NULL CHECK (status IN ('pending', 'onboarded', 'separated', 'cancelled')),
                        requested_at TEXT NOT NULL,
                        onboarded_at TEXT,
                        separated_at TEXT,
                        separation_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS attendance_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL REFERENCES projects(id),
                        snapshot_date TEXT NOT NULL,
                        on_duty_count INTEGER NOT NULL CHECK (on_duty_count >= 0),
                        source TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(project_id, snapshot_date)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL REFERENCES projects(id),
                        actor_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        object_type TEXT NOT NULL,
                        object_id TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE
                    )
                    """
                )

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
        """Add a missing column without rewriting existing local demo data."""
        column = definition.split()[0]
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
