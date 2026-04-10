"""그래프 상태 정의 (seed.yaml ontology_schema 대응)."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class StudySpotState(TypedDict, total=False):
    study_mode: Literal["solo", "team"]
    location_text: str
    search_radius: NotRequired[int]
    # WGS84
    lat: NotRequired[float]
    lng: NotRequired[float]
    address_label: NotRequired[str]
    candidates: NotRequired[list[dict]]
    ranked: NotRequired[list[dict]]
    enrich_used: NotRequired[bool]
    enrich_note: NotRequired[str]
    final_markdown: NotRequired[str]
    error: NotRequired[str | None]
    logs: NotRequired[list[str]]
