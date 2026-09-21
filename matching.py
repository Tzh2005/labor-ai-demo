"""Explainable, local candidate-to-job matching for the MVP."""

from __future__ import annotations

import re
from typing import Any


def _terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", value.lower()) if term}


def match_candidate_to_jobs(candidate: dict[str, Any], jobs: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Rank jobs by transparent field matches; no model or external service is used."""
    candidate_position = str(candidate.get("preferred_position", "")).strip()
    candidate_location = str(candidate.get("preferred_location", "")).strip()
    candidate_terms = _terms(str(candidate.get("skills", "")))
    ranked: list[dict[str, Any]] = []
    for job in jobs:
        reasons: list[str] = []
        score = 0
        if candidate_position and candidate_position in str(job.get("position", "")):
            score += 45
            reasons.append("岗位方向匹配")
        if candidate_location and candidate_location in str(job.get("location", "")):
            score += 30
            reasons.append("工作地区匹配")
        job_terms = _terms(" ".join(str(job.get(field, "")) for field in ("position", "requirements", "benefits")))
        overlap = candidate_terms & job_terms
        if overlap:
            score += min(25, len(overlap) * 8)
            reasons.append(f"技能/要求匹配 {len(overlap)} 项")
        if score:
            ranked.append({"job": job, "score": min(score, 100), "reasons": reasons})
    ranked.sort(key=lambda item: (-item["score"], int(item["job"]["id"])))
    return ranked[:limit]
