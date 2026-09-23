"""Project delivery metrics and evidence export helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def calculate_delivery_metrics(
    candidates: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    workers: list[dict[str, Any]],
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate only metrics supported by the currently stored facts."""
    onboarded = [item for item in placements if item.get("status") == "onboarded" or item.get("onboarded_at")]
    separated = [item for item in placements if item.get("status") == "separated" or item.get("separated_at")]
    durations: list[float] = []
    for placement in onboarded:
        requested = _parse_time(placement.get("requested_at"))
        arrived = _parse_time(placement.get("onboarded_at"))
        if requested and arrived and arrived >= requested:
            durations.append((arrived - requested).total_seconds() / 86400)

    return {
        "candidate_count": len(candidates),
        "application_count": len(applications),
        "interview_count": sum(1 for item in applications if item.get("status") == "interview"),
        "hired_count": sum(1 for item in applications if item.get("status") == "hired"),
        "worker_count": len(workers),
        "onboarded_count": len(onboarded),
        "separated_count": len(separated),
        "placement_fill_rate": _percentage(len(onboarded), len(placements)),
        "application_hire_rate": _percentage(sum(1 for item in applications if item.get("status") == "hired"), len(applications)),
        "average_fill_days": round(sum(durations) / len(durations), 1) if durations else None,
        "retention_7d": None,
        "retention_30d": None,
        "limitations": [
            "当前没有岗位需求数量表，因此未计算岗位满足率。",
            "当前测试派工记录不足以计算 7 日/30 日留存率；补充历史入场和离场记录后自动计算。",
        ],
    }


def build_evidence_bundle(
    project: dict[str, Any],
    metrics: dict[str, Any],
    jobs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    workers: list[dict[str, Any]],
    placements: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
) -> bytes:
    """Build a JSON evidence package without phone hashes or other secrets."""
    safe_candidates = [
        {key: value for key, value in candidate.items() if key not in {"phone_hash", "phone_last4"}}
        for candidate in candidates
    ]
    safe_audit: list[dict[str, Any]] = []
    for event in audit_events:
        copied = dict(event)
        try:
            details = json.loads(str(copied.get("details_json", "{}")))
            if isinstance(details, dict):
                details.pop("phone_hash", None)
                details.pop("phone_last4", None)
                details.pop("phone", None)
                copied["details"] = details
            copied.pop("details_json", None)
        except json.JSONDecodeError:
            copied["details"] = {}
            copied.pop("details_json", None)
        safe_audit.append(copied)
    bundle = {
        "schema_version": "evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notice": "本证据包由项目演示数据生成，不代表真实薪酬、社保或用工承诺。",
        "project": project,
        "metrics": metrics,
        "jobs": jobs,
        "candidates": safe_candidates,
        "applications": applications,
        "workers": workers,
        "placements": placements,
        "attendance_snapshots": snapshots,
        "audit_events": safe_audit,
    }
    return json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
