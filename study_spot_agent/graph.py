"""
LangGraph StateGraph — 지오코딩 → 검색 → (solo|team) 점수 노드 분기 → enrich 조건 분기 → 최종화.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Literal

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from study_spot_agent.kakao import collect_study_spot_candidates, geocode_address
from study_spot_agent.scoring import score_places, should_enrich
from study_spot_agent.state import StudySpotState


def _log(state: StudySpotState, line: str) -> list[str]:
    logs = list(state.get("logs") or [])
    logs.append(line)
    return logs


def node_geocode(state: StudySpotState) -> dict[str, Any]:
    logs = _log(state, "노드 geocode: 주소 검색 시작")
    res = geocode_address(state.get("location_text", ""))
    if not res.get("ok"):
        err = str(res.get("error", "알 수 없는 오류"))
        logs.append(f"geocode 실패: {err}")
        return {"error": err, "logs": logs, "final_markdown": f"**오류:** {err}"}

    logs.append(f"geocode 성공: {res.get('address_label')} (lat={res['lat']}, lng={res['lng']})")
    return {
        "lat": res["lat"],
        "lng": res["lng"],
        "address_label": res.get("address_label", ""),
        "error": None,
        "logs": logs,
    }


def node_search(state: StudySpotState) -> dict[str, Any]:
    logs = _log(state, "노드 search: 카페·도서관 후보 수집")
    lat, lng = state.get("lat"), state.get("lng")
    if lat is None or lng is None:
        logs.append("좌표 없음 — search 생략")
        return {"candidates": [], "logs": logs}
    radius = int(state.get("search_radius") or 3000)
    res = collect_study_spot_candidates(float(lat), float(lng), radius=radius)
    if res.get("errors"):
        for e in res["errors"]:
            logs.append(f"검색 부분 오류: {e}")
    places = res.get("places") or []
    logs.append(f"후보 {len(places)}개 수집")
    return {"candidates": places, "logs": logs}


def node_score_solo(state: StudySpotState) -> dict[str, Any]:
    logs = _log(state, "노드 score_solo: 혼자 모드 규칙 점수")
    ranked = score_places(state.get("candidates") or [], "solo")
    logs.append(f"랭킹 완료 (solo), 상위 점수: {ranked[0]['score'] if ranked else 'N/A'}")
    return {"ranked": ranked, "logs": logs}


def node_score_team(state: StudySpotState) -> dict[str, Any]:
    logs = _log(state, "노드 score_team: 팀 모드 규칙 점수")
    ranked = score_places(state.get("candidates") or [], "team")
    logs.append(f"랭킹 완료 (team), 상위 점수: {ranked[0]['score'] if ranked else 'N/A'}")
    return {"ranked": ranked, "logs": logs}


def node_enrich(state: StudySpotState) -> dict[str, Any]:
    logs = _log(state, "노드 enrich: 저신뢰 구간 — LLM 체크리스트(추정) 보강")
    ranked = state.get("ranked") or []
    top = ranked[:3]
    if not os.getenv("OPENAI_API_KEY"):
        note = (
            "OPENAI_API_KEY가 없어 LLM 보강을 건너뜁니다. "
            "아래 공통 체크리스트만 제공합니다.\n\n"
            "- 콘센트·좌석·소음은 방문 전 확인이 필요합니다(추정 아님 실측).\n"
            "- 영업시간·휴무는 지도 앱에서 재확인하세요."
        )
        logs.append("enrich: OpenAI 키 없음, 정적 노트만")
        return {"enrich_used": True, "enrich_note": note, "logs": logs}

    lines = [f"- {r.get('place_name')} ({r.get('category_name')})" for r in top]
    prompt = (
        "다음은 지도 API로 얻은 장소 이름/카테고리일 뿐, 좌석·소음·콘센트는 알 수 없습니다.\n"
        "사실을 지어내지 말고, 사용자가 방문 전에 스스로 확인할 **체크리스트 5항목 이내**를 한국어로 bullet으로 작성하세요.\n"
        "각 항목은 '확인 필요' 톤으로 작성합니다.\n\n"
        + "\n".join(lines)
    )
    llm = ChatOpenAI(model="gpt-5-mini")
    out = llm.invoke([HumanMessage(content=prompt)])
    note = (out.content or "").strip()
    logs.append("enrich: LLM 체크리스트 생성")
    return {"enrich_used": True, "enrich_note": note, "logs": logs}


def node_finalize(state: StudySpotState) -> dict[str, Any]:
    logs = _log(state, "노드 finalize: 마크다운 응답 조립")
    if state.get("error") and not state.get("ranked"):
        return {"logs": logs}

    ranked = state.get("ranked") or []
    lines: list[str] = []
    lines.append(f"## 추천 결과 (모드: **{state.get('study_mode', '')}**)")
    lines.append(
        f"기준 위치: **{state.get('address_label', state.get('location_text', ''))}** "
        "(주소 API 기준, 검증됨)"
    )
    lines.append("")
    if not ranked:
        lines.append("_검색된 후보가 없습니다. 반경을 넓히거나 다른 지역으로 시도해 보세요._")
    for i, r in enumerate(ranked[:8], 1):
        v = ", ".join(r.get("verified") or [])
        lines.append(
            f"{i}. **{r.get('place_name')}** — 점수 `{r.get('score')}` "
            f"· 거리 약 {r.get('distance', '?')}m · 카테고리: {r.get('category_name')}\n"
            f"   - 근거(규칙): {', '.join(r.get('reasons') or [])}\n"
            f"   - 검증된 필드: {v or '없음'}; 나머지는 **추정 아님 미확인**\n"
            f"   - 링크: {r.get('place_url') or '없음'}"
        )
    lines.append("")
    if state.get("enrich_note"):
        lines.append("### 방문 전 체크 (일부 LLM 생성, 사실 단정 아님)")
        lines.append(state["enrich_note"])
        lines.append("")
    lines.append(
        "### 고지\n"
        "좌석/소음/콘센트/혼잡도는 실시간 변동이 큽니다. "
        "‘검증됨’은 주로 **거리·카테고리명** 등 API 제공 필드에 한합니다."
    )
    md = "\n".join(lines)
    logs.append("finalize 완료")
    return {"final_markdown": md, "logs": logs}


def route_after_geocode(state: StudySpotState) -> Literal["search", "end"]:
    if state.get("error"):
        return "end"
    return "search"


def route_study_mode(state: StudySpotState) -> Literal["score_solo", "score_team"]:
    return "score_team" if state.get("study_mode") == "team" else "score_solo"


def route_after_score(state: StudySpotState) -> Literal["enrich", "finalize"]:
    ranked = state.get("ranked") or []
    if should_enrich(ranked):
        return "enrich"
    return "finalize"


def build_graph():
    g = StateGraph(StudySpotState)
    g.add_node("geocode", node_geocode)
    g.add_node("search", node_search)
    g.add_node("score_solo", node_score_solo)
    g.add_node("score_team", node_score_team)
    g.add_node("enrich", node_enrich)
    g.add_node("finalize", node_finalize)

    g.add_edge(START, "geocode")
    g.add_conditional_edges("geocode", route_after_geocode, {"search": "search", "end": "finalize"})
    g.add_conditional_edges(
        "search",
        route_study_mode,
        {"score_solo": "score_solo", "score_team": "score_team"},
    )
    g.add_conditional_edges(
        "score_solo",
        route_after_score,
        {"enrich": "enrich", "finalize": "finalize"},
    )
    g.add_conditional_edges(
        "score_team",
        route_after_score,
        {"enrich": "enrich", "finalize": "finalize"},
    )
    g.add_edge("enrich", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


def new_run_id() -> str:
    return str(uuid.uuid4())[:8]
