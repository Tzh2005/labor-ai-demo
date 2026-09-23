"""Idempotent seed data for the local project-delivery demo.

The records are synthetic and clearly labelled. This module must never be used
for importing customer or worker data; use an authorized import pipeline for
that later.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from conversation_store import ConversationStore


SEED_PREFIX = "测试工人·"


def seed_demo_data(store: ConversationStore, project_id: str = ConversationStore.DEFAULT_PROJECT_ID) -> dict[str, int]:
    """Create synthetic project records once and return the resulting counts."""
    root = Path(__file__).resolve().parent
    store.sync_jobs_from_file(root / "data" / "jobs.json", project_id=project_id)
    existing = {item["name"]: item for item in store.list_candidates(project_id)}
    candidate_specs = [
        ("张三", "19900000001", 25, "男", "石岩", "普工", "电子厂经验、包装"),
        ("李四", "19900000002", 29, "女", "松岗", "车位工", "制衣经验"),
        ("王五", "19900000003", 32, "男", "公明", "车床工", "车床、看图纸"),
        ("赵六", "19900000004", 23, "男", "石岩", "包装工", "包装、流水线"),
        ("陈七", "19900000005", 27, "女", "龙华", "SMT操作工", "电子厂、质检"),
    ]
    candidates: list[dict[str, Any]] = []
    for name, phone, age, gender, location, position, skills in candidate_specs:
        display_name = f"{SEED_PREFIX}{name}"
        candidate = existing.get(display_name)
        if candidate is None:
            candidate_id = store.create_candidate(name=display_name, phone=phone, age=age, gender=gender, preferred_location=location, preferred_position=position, skills=skills, project_id=project_id, actor_id="demo_seed")
            candidate = next(item for item in store.list_candidates(project_id) if item["id"] == candidate_id)
        candidates.append(candidate)

    applications_by_key = {(item["candidate_id"], item["job_id"]): item for item in store.list_applications(project_id)}
    application_plan = [(0, 1, "hired"), (1, 2, "interview"), (2, 3, "hired"), (3, 6, "applied"), (4, 7, "rejected")]
    applications: list[dict[str, Any]] = []
    for candidate_index, job_id, status in application_plan:
        candidate_id = int(candidates[candidate_index]["id"])
        application_id = store.create_application(candidate_id, job_id, project_id=project_id, actor_id="demo_seed")
        current = applications_by_key.get((candidate_id, job_id))
        if current is None or current["status"] != status:
            store.update_application_status(application_id, status, project_id=project_id, actor_id="demo_seed")
        applications_by_key = {(item["candidate_id"], item["job_id"]): item for item in store.list_applications(project_id)}
        applications.append(next(item for item in store.list_applications(project_id) if item["id"] == application_id))

    workers_by_candidate = {item["candidate_id"]: item for item in store.list_workers(project_id)}
    placement_plan = [(0, 1, "onboarded"), (2, 3, "separated"), (3, 6, "pending")]
    placements = store.list_placements(project_id)
    for candidate_index, job_id, status in placement_plan:
        candidate_id = int(candidates[candidate_index]["id"])
        worker = workers_by_candidate.get(candidate_id)
        if worker is None:
            worker_id = store.promote_candidate_to_worker(candidate_id, project_id=project_id, source_channel="demo_seed", actor_id="demo_seed")
            worker = next(item for item in store.list_workers(project_id) if item["id"] == worker_id)
            workers_by_candidate[candidate_id] = worker
        placement = next((item for item in placements if item["worker_id"] == worker["id"] and item["job_id"] == job_id), None)
        if placement is None:
            placement_id = store.create_placement(worker["id"], job_id, project_id=project_id, actor_id="demo_seed")
            placement = {"id": placement_id, "status": "pending"}
            placements = store.list_placements(project_id)
        if placement["status"] != status:
            store.update_placement_status(placement["id"], status, "测试数据：自然离场" if status == "separated" else "", project_id=project_id, actor_id="demo_seed")

    today = date.today()
    for offset, count in ((2, 2), (1, 2), (0, 1)):
        snapshot_date = (today - timedelta(days=offset)).isoformat()
        if not any(item["snapshot_date"] == snapshot_date for item in store.list_attendance_snapshots(project_id)):
            store.save_attendance_snapshot(snapshot_date, count, source="demo_seed", project_id=project_id, actor_id="demo_seed")

    return {
        "candidates": len(store.list_candidates(project_id)),
        "applications": len(store.list_applications(project_id)),
        "workers": len(store.list_workers(project_id)),
        "placements": len(store.list_placements(project_id)),
        "snapshots": len(store.list_attendance_snapshots(project_id)),
    }


if __name__ == "__main__":
    print(seed_demo_data(ConversationStore()))
