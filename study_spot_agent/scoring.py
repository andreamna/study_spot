"""규칙 기반 점수 — solo / team 가중 (seed: 중간 결과에 따른 분기)."""

from __future__ import annotations

from typing import Any, Literal


def _dist_m(p: dict[str, Any]) -> float:
    try:
        return float(p.get("distance") or 1e9)
    except (TypeError, ValueError):
        return 1e9


def score_places(
    places: list[dict[str, Any]],
    mode: Literal["solo", "team"],
) -> list[dict[str, Any]]:
    """후보에 score, reasons, verified 필드 추가 후 점수 내림차순."""
    ranked: list[dict[str, Any]] = []
    for p in places:
        s, reasons = _score_one(p, mode)
        row = {**p, "score": s, "reasons": reasons, "verified": ["distance", "category_name"]}
        ranked.append(row)
    ranked.sort(key=lambda x: (-x["score"], _dist_m(x)))
    return ranked


def _score_one(p: dict[str, Any], mode: Literal["solo", "team"]) -> tuple[float, list[str]]:
    cat = (p.get("category_name") or "") + " " + (p.get("place_name") or "")
    cg = p.get("category_group_code") or ""
    dist = _dist_m(p)
    reasons: list[str] = []
    score = 0.0

    if "도서관" in cat:
        score += 5.0 if mode == "solo" else 4.0
        reasons.append("도서관 카테고리(조용한 학습에 유리할 수 있음)")
    if "카페" in cat or cg == "CE7":
        score += 2.5 if mode == "solo" else 3.5
        reasons.append("카페 카테고리")
    if mode == "team":
        score += 1.0
        reasons.append("팀 모드: 대화 가능 업종 가중(추정)")
    if mode == "solo":
        score += 1.0
        reasons.append("혼자 모드: 집중 가중(추정)")

    # 거리: 가까울수록 가산 (최대 +3)
    dist_bonus = max(0.0, 3.0 - min(dist, 3000.0) / 1000.0)
    score += dist_bonus
    if dist_bonus > 0:
        reasons.append(f"거리 가산(약 {int(dist)}m)")

    # 페널티(추정 키워드)
    bad = ("주점", "유흥", "노래방", "클럽")
    if any(b in cat for b in bad):
        score -= 4.0
        reasons.append("업종 키워드로 인한 감점(추정)")

    return round(score, 2), reasons


def should_enrich(ranked: list[dict[str, Any]], score_threshold: float = 5.0, min_count: int = 2) -> bool:
    """상위 점수 낮거나 후보 부족 시 enrich 분기."""
    if len(ranked) < min_count:
        return True
    top = ranked[0].get("score") or 0.0
    return float(top) < score_threshold
