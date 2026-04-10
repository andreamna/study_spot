"""
공부 장소 추천 — seed.yaml 기반 LangGraph + Streamlit UI.
실행 (notebooks 폴더에서): streamlit run study_spot_streamlit.py

필요 환경변수:
- KAKAO_REST_API_KEY (필수)
- OPENAI_API_KEY (enrich LLM 선택, 없으면 정적 체크리스트만)
"""
from __future__ import annotations

import html
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

import folium
from streamlit_folium import st_folium

from study_spot_agent.feedback_store import append_feedback, feedback_path  # noqa: E402
from study_spot_agent.graph import build_graph, new_run_id  # noqa: E402


@st.cache_resource
def get_compiled_graph():
    return build_graph()


def _inject_theme_css() -> None:
    st.markdown(
        """
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,500&display=swap');

  html, body, [class*="css"]  {
    font-family: 'DM Sans', 'Malgun Gothic', sans-serif;
  }

  .stApp {
    background: linear-gradient(
      165deg,
      #fff5eb 0%,
      #e8f4fc 28%,
      #ecf8f4 58%,
      #fff9e6 100%
    );
  }

  .stApp > header { background: transparent; }

  section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #243b53 0%, #1e3044 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
  }
  section[data-testid="stSidebar"] * {
    color: #e2ecf5;
  }
  section[data-testid="stSidebar"] .stMarkdown a {
    color: #7dd3fc;
  }
  section[data-testid="stSidebar"] small,
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #a8bfd4 !important;
  }

  .sb-head {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #fff !important;
    margin-bottom: 0.75rem;
  }
  .sb-pill-wrap { margin: 0.5rem 0 0.25rem 0; }
  .sb-pill {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.65rem;
    margin-bottom: 0.35rem;
    border-radius: 10px;
    background: rgba(255,255,255,0.08);
    font-size: 0.88rem;
  }
  .sb-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .sb-dot.on { background: #4ade80; box-shadow: 0 0 8px rgba(74,222,128,0.5); }
  .sb-dot.off { background: #f87171; }
  .sb-path-hint {
    font-size: 0.78rem;
    opacity: 0.85;
    word-break: break-all;
    line-height: 1.35;
    color: #b8d0e3 !important;
  }

  h1 {
    background: linear-gradient(90deg, #0f4c75 0%, #3282b8 50%, #197278 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 700 !important;
  }

  .page-lead {
    color: #355070;
    font-size: 1rem;
    margin-top: -0.25rem;
  }

  .col-heading {
    font-size: 1.35rem;
    font-weight: 700;
    margin: 1rem 0 0.75rem 0;
    padding: 0.5rem 0 0.5rem 14px;
    border-radius: 8px;
  }
  .col-heading.cafe {
    color: #9c4221;
    background: linear-gradient(90deg, rgba(255,180,120,0.35), transparent);
    border-left: 4px solid #ea580c;
  }
  .col-heading.library {
    color: #0f5132;
    background: linear-gradient(90deg, rgba(110,200,170,0.35), transparent);
    border-left: 4px solid #0d9488;
  }

  .place-card {
    background: rgba(255,255,255,0.92);
    border: 1px solid rgba(15,76,117,0.12);
    border-radius: 16px;
    padding: 1rem 1.1rem 0.85rem;
    margin-bottom: 1rem;
    box-shadow: 0 6px 20px rgba(15, 76, 117, 0.08);
  }
  .place-card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 0.65rem;
  }
  .place-name {
    margin: 0;
    font-size: 1.45rem;
    font-weight: 700;
    line-height: 1.25;
    color: #0f2744;
    letter-spacing: -0.03em;
  }
  .score-pill {
    flex-shrink: 0;
    text-align: right;
    padding: 0.35rem 0.75rem 0.45rem;
    border-radius: 14px;
    background: linear-gradient(135deg, #3282b8 0%, #0f4c75 100%);
    color: #fff;
    box-shadow: 0 4px 14px rgba(50,130,184,0.35);
    min-width: 4.5rem;
  }
  .score-pill .sl {
    display: block;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    opacity: 0.9;
  }
  .score-pill .sv {
    display: block;
    font-size: 1.65rem;
    font-weight: 800;
    line-height: 1;
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
  }
  .place-meta {
    font-size: 0.82rem;
    color: #5a6d82;
    margin-bottom: 0.5rem;
    line-height: 1.4;
  }
  .place-reasons-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: #3282b8;
    margin: 0.35rem 0 0.25rem;
  }
  .place-reasons {
    margin: 0 0 0.5rem 1rem;
    padding: 0;
    color: #3d5266;
    font-size: 0.88rem;
  }
  .place-foot {
    font-size: 0.78rem;
    color: #7d8fa3;
    margin: 0.35rem 0 0.35rem;
  }
  .result-hero {
    font-size: 1.75rem;
    font-weight: 700;
    color: #0f2744;
    margin-bottom: 0.35rem;
  }
  .result-sub {
    color: #4a6080;
    margin-bottom: 1rem;
  }
  .fineprint {
    font-size: 0.85rem;
    color: #5a6d82;
    margin-top: 1.25rem;
  }

  div.stButton > button[kind="primary"] {
    background: linear-gradient(95deg, #ea580c 0%, #c2410c 55%, #b45309 100%) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 14px rgba(234, 88, 12, 0.35);
  }
</style>
""",
        unsafe_allow_html=True,
    )


def _is_cafe(p: dict) -> bool:
    """카카오 CE7(카페) 또는 카테고리/이름에 카페 힌트."""
    cg = (p.get("category_group_code") or "").upper()
    cat = (p.get("category_name") or "") + " " + (p.get("place_name") or "")
    if cg == "CE7":
        return True
    if "카페" in cat or "카페트" in cat:
        return True
    if "북카페" in cat or "book cafe" in cat.lower():
        return True
    return False


def _split_ranked(ranked: list[dict]) -> tuple[list[dict], list[dict]]:
    cafes = [p for p in ranked if _is_cafe(p)]
    others = [p for p in ranked if not _is_cafe(p)]
    return cafes, others


def _parse_lat_lng(p: dict) -> tuple[float, float] | None:
    """Kakao keyword results use x=lng, y=lat (WGS84)."""
    try:
        lat = float(p.get("y"))
        lng = float(p.get("x"))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError):
        pass
    return None


def _filter_by_category_choice(ranked: list[dict], choice: str) -> list[dict]:
    if choice == "카페만":
        return [p for p in ranked if _is_cafe(p)]
    if choice == "도서관·기타만":
        return [p for p in ranked if not _is_cafe(p)]
    return list(ranked)


def _render_folium_map(
    places: list[dict],
    center_lat: float,
    center_lng: float,
) -> None:
    """Static map: center pin + cafe (orange) vs library/other (green). Uses OpenStreetMap tiles."""
    if not places:
        st.caption("지도에 표시할 좌표가 있는 추천이 없습니다.")
        return
    m = folium.Map(location=[center_lat, center_lng], zoom_start=15, tiles="OpenStreetMap")
    folium.Marker(
        [center_lat, center_lng],
        popup=folium.Popup("검색 기준 위치", max_width=220),
        tooltip="기준점",
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(m)

    bounds: list[list[float]] = [[center_lat, center_lng]]
    for p in places[:40]:
        coords = _parse_lat_lng(p)
        if not coords:
            continue
        lat, lng = coords
        bounds.append([lat, lng])
        cafe = _is_cafe(p)
        color = "#ea580c" if cafe else "#0d9488"
        name = str(p.get("place_name") or "?")
        score = p.get("score", "")
        dist = p.get("distance", "")
        url = str(p.get("place_url") or "").strip()
        link_html = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">Kakao Map</a>' if url else ""
        popup_html = (
            f"<strong>{html.escape(name)}</strong><br/>"
            f"점수: {html.escape(str(score))} · 약 {html.escape(str(dist))}m<br/>"
            f"{link_html}"
        )
        folium.CircleMarker(
            location=[lat, lng],
            radius=10,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=2,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{name[:28]}…" if len(name) > 28 else name,
        ).add_to(m)

    if len(bounds) > 1:
        m.fit_bounds(bounds, padding=(24, 24), max_zoom=16)

    st_folium(m, use_container_width=True, height=420, returned_objects=[])


def _render_place_card(p: dict) -> None:
    name = html.escape(str(p.get("place_name") or "(이름 없음)"))
    score = html.escape(str(p.get("score")))
    cat = html.escape(str(p.get("category_name") or "—"))
    dist = html.escape(str(p.get("distance") or "?"))
    reasons = p.get("reasons") or []
    lis = "".join(f"<li>{html.escape(str(line))}</li>" for line in reasons)
    reasons_block = (
        f'<p class="place-reasons-title">추천 근거 (규칙)</p><ul class="place-reasons">{lis}</ul>'
        if reasons
        else ""
    )
    st.markdown(
        f"""<div class="place-card">
  <div class="place-card-head">
    <h3 class="place-name">{name}</h3>
    <div class="score-pill"><span class="sl">점수</span><span class="sv">{score}</span></div>
  </div>
  <div class="place-meta">{cat} · 약 {dist}m · 검증: 거리·카테고리(API)</div>
  {reasons_block}
  <p class="place-foot">좌석·소음·콘센트는 미확인 — 방문 전 확인</p>
</div>""",
        unsafe_allow_html=True,
    )
    url = p.get("place_url") or ""
    if url:
        st.link_button("카카오맵에서 열기", url, use_container_width=True)


def _render_result_cards(state: dict) -> None:
    ranked = state.get("ranked") or []
    mode_ko = "혼자 집중" if state.get("study_mode") == "solo" else "팀플·소규모"
    loc = state.get("address_label") or state.get("location_text") or ""

    if state.get("error") and not ranked:
        st.error(state.get("error") or "요청 처리 중 오류가 났습니다.")
        return

    if not ranked:
        st.warning("이번 조건으로는 추천할 장소가 없습니다. 반경을 넓히거나 주소를 바꿔 보세요.")
        return

    loc_e = html.escape(str(loc))
    mode_e = html.escape(str(mode_ko))
    st.markdown(
        f'<p class="result-hero">추천 · <span style="color:#3282b8">{mode_e}</span></p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p class='result-sub'>기준 위치: <strong>{loc_e}</strong> (주소 API) · "
        f"점수 순 · 아래에서 <strong>표시 필터</strong>와 <strong>지도</strong>를 조정할 수 있습니다.</p>",
        unsafe_allow_html=True,
    )

    cafes_all, others_all = _split_ranked(ranked)
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("전체 추천", len(ranked))
    with m2:
        st.metric("카페", len(cafes_all))
    with m3:
        st.metric("도서관·기타", len(others_all))

    cat_choice = st.radio(
        "표시 카테고리",
        ["전체", "카페만", "도서관·기타만"],
        horizontal=True,
        help="목록·지도 모두 이 필터가 적용됩니다.",
    )
    filtered = _filter_by_category_choice(ranked, cat_choice)
    st.caption(f"지금 표시: **{len(filtered)}**곳 (카드·지도 동일)")

    cen_lat, cen_lng = state.get("lat"), state.get("lng")
    if cen_lat is not None and cen_lng is not None and filtered:
        st.subheader("지도")
        st.caption("파란 핀: 검색 기준 · 주황: 카페 · 청록: 도서관·기타")
        _render_folium_map(filtered, float(cen_lat), float(cen_lng))
        st.divider()

    cafes, others = _split_ranked(filtered)

    col_cafe, col_other = st.columns(2, gap="large")
    with col_cafe:
        st.markdown('<div class="col-heading cafe">카페</div>', unsafe_allow_html=True)
        if not cafes:
            st.caption("_반경 안에 카페 후보가 없거나, 모두 아래 ‘기타’로 분류됐습니다._")
        else:
            for p in cafes:
                _render_place_card(p)
    with col_other:
        st.markdown('<div class="col-heading library">도서관 · 기타</div>', unsafe_allow_html=True)
        if not others:
            st.caption("_도서관·독서실 등 후보가 없습니다._")
        else:
            for p in others:
                _render_place_card(p)

    if state.get("enrich_note"):
        with st.expander("방문 전 체크 (enrich · 추정 포함)", expanded=False):
            st.markdown(state["enrich_note"])

    st.markdown(
        "<p class='fineprint'>"
        "실시간 좌석·혼잡도는 반영하지 않습니다. 표시된 ‘검증’은 카카오 API 필드 기준입니다."
        "</p>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="공부 장소 추천", layout="wide")
    _inject_theme_css()
    st.title("공부 장소 추천 에이전트")
    st.markdown(
        '<p class="page-lead">LangGraph 워크플로 · 카카오 로컬 API · solo/team 분기 · 조건부 enrich</p>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown('<p class="sb-head">설정</p>', unsafe_allow_html=True)
        k_ok = bool(os.getenv("KAKAO_REST_API_KEY"))
        o_ok = bool(os.getenv("OPENAI_API_KEY"))
        st.markdown(
            f"""<div class="sb-pill-wrap">
<div class="sb-pill"><span class="sb-dot {'on' if k_ok else 'off'}"></span><span>Kakao API · {'연결됨' if k_ok else '미설정'}</span></div>
<div class="sb-pill"><span class="sb-dot {'on' if o_ok else 'off'}"></span><span>OpenAI · {'연결됨' if o_ok else 'enrich 생략 가능'}</span></div>
</div>""",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown('<p class="sb-head" style="font-size:0.95rem">피드백 로그</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sb-path-hint">파일명 <code style="color:#a5d8ff">feedback.jsonl</code><br/>폴더 <code style="color:#a5d8ff">study_spot_data/</code></p>',
            unsafe_allow_html=True,
        )
        with st.expander("전체 경로", expanded=False):
            st.code(str(feedback_path()), language=None)

    col1, col2 = st.columns(2)
    with col1:
        mode = st.radio(
            "공부 모드 (그래프 분기)",
            ["solo", "team"],
            format_func=lambda x: "혼자 집중" if x == "solo" else "팀플·소규모",
            horizontal=True,
        )
    with col2:
        radius = st.slider("검색 반경 (m)", 500, 8000, 3000, step=100)

    location = st.text_input(
        "주소 / 지명",
        value="부산 금정구 장전동",
        placeholder="주소·동 이름 또는 장소명 (예: 부산 금정구 장전동, 부산대, 서울역 …)",
    )

    run = st.button("추천 실행", type="primary")

    if "run_id" not in st.session_state:
        st.session_state.run_id = new_run_id()
    if "last_state" not in st.session_state:
        st.session_state.last_state = None

    if run:
        st.session_state.run_id = new_run_id()
        if not location.strip():
            st.warning("주소·지명을 입력하세요.")
            return
        if not os.getenv("KAKAO_REST_API_KEY"):
            st.error("`.env`에 `KAKAO_REST_API_KEY`를 설정하세요 (카카오 개발자 REST 키).")
            return

        graph = get_compiled_graph()
        init: dict = {
            "study_mode": mode,
            "location_text": location.strip(),
            "search_radius": radius,
            "logs": [],
        }
        try:
            with st.spinner("LangGraph 실행 중… (지오코딩 → 검색 → 점수 → enrich 분기)"):
                out = graph.invoke(init)
        except Exception as e:
            st.exception(e)
            return
        st.session_state.last_state = out

    state = st.session_state.last_state
    if not state:
        st.info("주소를 입력하고 **추천 실행**을 누르세요.")
        return

    _render_result_cards(state)

    with st.expander("투명성: 실행 로그 (노드 순서)", expanded=False):
        for line in state.get("logs") or []:
            st.text(line)

    with st.expander("원본 후보 (일부)", expanded=False):
        st.json((state.get("candidates") or [])[:15])

    st.divider()
    st.subheader("피드백 (👍 / 👎)")
    ranked = state.get("ranked") or []
    if not ranked:
        st.caption("피드백할 추천이 없습니다.")
        return

    choices = {f"{r.get('place_name')} (점수 {r.get('score')})": r for r in ranked[:8]}
    label = st.selectbox("장소 선택", list(choices.keys()))
    fc1, fc2 = st.columns(2)
    with fc1:
        if st.button("👍 도움됨"):
            r = choices[label]
            append_feedback(
                run_id=st.session_state.run_id,
                study_mode=state.get("study_mode", ""),
                location_text=state.get("location_text", ""),
                place_id=str(r.get("id") or ""),
                place_name=str(r.get("place_name") or ""),
                vote="up",
                extra={"score": r.get("score"), "enrich_used": state.get("enrich_used")},
            )
            st.toast("피드백을 저장했습니다.", icon="👍")
            st.success("저장했습니다.")
    with fc2:
        if st.button("👎 별로"):
            r = choices[label]
            append_feedback(
                run_id=st.session_state.run_id,
                study_mode=state.get("study_mode", ""),
                location_text=state.get("location_text", ""),
                place_id=str(r.get("id") or ""),
                place_name=str(r.get("place_name") or ""),
                vote="down",
                extra={"score": r.get("score"), "enrich_used": state.get("enrich_used")},
            )
            st.toast("피드백을 저장했습니다.", icon="👎")
            st.success("저장했습니다.")


if __name__ == "__main__":
    main()
