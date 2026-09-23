"""Deterministic project-delivery risk rules.

The rules produce operational signals; RAG can later explain them from
project documents. They do not make legal or employment decisions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def assess_project_risks(
    jobs: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    placements: list[dict[str, Any]],
    now: datetime | None = None,
    stale_after_days: int = 7,
) -> list[dict[str, str]]:
    """Return explainable delivery risks ordered by severity and title."""
    now = now or datetime.now(timezone.utc)
    applications_by_job: dict[int, int] = {}
    for application in applications:
        job_id = int(application["job_id"])
        applications_by_job[job_id] = applications_by_job.get(job_id, 0) + 1

    risks: list[dict[str, str]] = []
    for job in jobs:
        job_id = int(job["id"])
        if applications_by_job.get(job_id, 0) == 0:
            risks.append({
                "severity": "medium",
                "code": "no_candidate",
                "title": f"岗位暂无候选人：{job['factory_name']} · {job['position']}",
                "detail": "当前项目没有报名记录，可能影响岗位交付。",
                "action": "确认岗位要求和渠道，优先补充候选人。",
            })

    stale_cutoff = now - timedelta(days=stale_after_days)
    for application in applications:
        if application.get("status") not in {"applied", "interview"}:
            continue
        updated_at = application.get("updated_at") or application.get("created_at")
        if not updated_at:
            continue
        try:
            updated = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if updated < stale_cutoff:
            risks.append({
                "severity": "high",
                "code": "stale_application",
                "title": f"报名状态超过 {stale_after_days} 天未推进：{application['name']}",
                "detail": f"{application['factory_name']} · {application['position']} 仍处于{application['status']}状态。",
                "action": "联系候选人或甲方确认下一步，并记录处理结果。",
            })

    active_placements = sum(1 for placement in placements if placement.get("status") == "onboarded")
    if placements and active_placements == 0:
        risks.append({
            "severity": "high",
            "code": "no_onboarded_worker",
            "title": "已有派工记录但暂无在岗人员",
            "detail": "派工流程尚未形成到岗结果，项目交付可能中断。",
            "action": "核对入场状态并补录到岗或取消原因。",
        })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(risks, key=lambda item: (severity_order.get(item["severity"], 9), item["title"]))


def group_dashboard_risks(
    risks: list[dict[str, str]],
    high_limit: int = 3,
    other_limit: int = 2,
) -> dict[str, list[dict[str, str]]]:
    """Group repetitive dashboard risks while preserving every original item.

    Missing-candidate signals are emitted once per position by the rules engine.
    The dashboard presents them as one operational backlog, while the full list
    remains available in the collapsed detail section.
    """
    high_risks = [risk for risk in risks if risk.get("severity") == "high"]
    no_candidate_risks = [risk for risk in risks if risk.get("code") == "no_candidate"]
    other_risks = [
        risk for risk in risks
        if risk.get("severity") != "high" and risk.get("code") != "no_candidate"
    ]
    return {
        "high": high_risks,
        "visible_high": high_risks[:max(0, high_limit)],
        "overflow_high": high_risks[max(0, high_limit):],
        "no_candidate": no_candidate_risks,
        "visible_other": other_risks[:max(0, other_limit)],
        "overflow_other": other_risks[max(0, other_limit):],
    }
