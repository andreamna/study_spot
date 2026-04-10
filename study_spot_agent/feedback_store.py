"""사용자 👍/👎 피드백 — JSON Lines 영속 저장 (seed acceptance)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def feedback_path() -> Path:
    base = Path(__file__).resolve().parent.parent
    d = base / "study_spot_data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "feedback.jsonl"


def append_feedback(
    *,
    run_id: str,
    study_mode: str,
    location_text: str,
    place_id: str | None,
    place_name: str,
    vote: str,
    extra: dict | None = None,
) -> None:
    path = feedback_path()
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "study_mode": study_mode,
        "location_text": location_text,
        "place_id": place_id,
        "place_name": place_name,
        "vote": vote,
        "extra": extra or {},
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
