"""Kakao Local API — 주소 검색(지오코딩) + 키워드 장소 검색."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# Keyword search with `rect`: lower-left lng,lat then upper-right lng,lat (WGS84).
# Covers mainland Korea when a global keyword query returns nothing.
_KOREA_RECT = "124.5,33.0,132.0,38.8"


def _headers() -> dict[str, str]:
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        raise RuntimeError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")
    return {"Authorization": f"KakaoAK {key}"}


def _prefer_keyword_geocode_first(q: str) -> bool:
    """
    주소 API가 '부산대' 같은 장소명을 엉뚱한 도로명/지번에 매칭하는 경우가 있어,
    행정구역/도로 패턴이 없으면 키워드(POI) 지오코딩을 먼저 시도한다.
    """
    q = q.strip()
    if not q or re.search(r"\d", q):
        return False
    parts = [p for p in re.split(r"[\s,]+", q) if p]
    for p in parts:
        if len(p) < 2:
            continue
        if p.endswith(("동", "가", "리", "읍", "면")):
            return False
        if len(p) >= 3 and p.endswith("구"):
            return False
        if p.endswith(("로", "길")):
            return False
    if len(parts) >= 3:
        return False
    return True


def _keyword_geocode_attempt(
    client: httpx.Client,
    query: str,
    extra_params: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """
    Returns (documents, error_message). documents is None if HTTP not usable.
    """
    params: dict[str, Any] = {"query": query, "size": 5, "sort": "accuracy", **extra_params}
    r = client.get(KEYWORD_URL, headers=_headers(), params=params)
    if r.status_code == 401:
        return None, "카카오 API 키가 거부되었습니다."
    if r.status_code != 200:
        return None, f"키워드 API HTTP {r.status_code}: {r.text[:200]}"
    data = r.json()
    return data.get("documents") or [], None


def geocode_by_keyword_place(query: str, timeout: float = 10.0) -> dict[str, Any]:
    """
    건물·캠퍼스·역 등 **장소 키워드** → 좌표 (키워드 검색 API).
    예: 부산대, 서울역 — 주소 검색(address.json)이 비어 있을 때 사용.
    순서: (1) 정확도 정렬 (2) 한국 영역 rect로 재시도.
    """
    q = query.strip()
    if not q:
        return {"ok": False, "error": "검색어가 비어 있습니다."}

    attempts: list[dict[str, Any]] = [
        {},
        {"rect": _KOREA_RECT},
    ]

    try:
        with httpx.Client(timeout=timeout) as client:
            docs: list[dict[str, Any]] | None = None
            last_err: str | None = None
            for extra in attempts:
                dlist, err = _keyword_geocode_attempt(client, q, extra)
                if err:
                    last_err = err
                    if "401" in err or "거부" in err:
                        return {"ok": False, "error": err}
                    continue
                if dlist:
                    docs = dlist
                    break
            if not docs:
                return {
                    "ok": False,
                    "error": last_err or "키워드 검색 결과가 없습니다.",
                }

    except Exception as e:
        return {"ok": False, "error": f"네트워크 오류: {e}"}

    d0 = docs[0]
    try:
        lng = float(d0["x"])
        lat = float(d0["y"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "error": "좌표 파싱에 실패했습니다."}

    place = (d0.get("place_name") or "").strip()
    road = (d0.get("road_address_name") or d0.get("address_name") or "").strip()
    if place and road:
        label = f"{place} — {road}"
    elif place:
        label = place
    elif road:
        label = road
    else:
        label = q

    return {
        "ok": True,
        "lat": lat,
        "lng": lng,
        "address_label": label,
        "raw": d0,
        "geocode_source": "keyword",
    }


def geocode_address(query: str, timeout: float = 10.0) -> dict[str, Any]:
    """
    주소 또는 장소명 → 좌표.
    - 행정동/도로형 입력: 주소 API 우선 → 비면 키워드.
    - 짧은 장소명(부산대, ○○역 등): 키워드 우선 → 비면 주소 API.
    """
    q = query.strip()
    if not q:
        return {"ok": False, "error": "주소·지명이 비어 있습니다."}

    keyword_first = _prefer_keyword_geocode_first(q)
    if keyword_first:
        kw = geocode_by_keyword_place(q, timeout=timeout)
        if kw.get("ok"):
            return kw

    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                ADDRESS_URL,
                headers=_headers(),
                params={"query": q, "size": 5},
            )
    except Exception as e:
        return {"ok": False, "error": f"네트워크 오류: {e}"}

    if r.status_code == 401:
        return {"ok": False, "error": "카카오 API 키가 거부되었습니다. KAKAO_REST_API_KEY를 확인하세요."}
    if r.status_code != 200:
        return {"ok": False, "error": f"주소 API HTTP {r.status_code}: {r.text[:200]}"}

    data = r.json()
    docs = data.get("documents") or []
    if docs:
        d0 = docs[0]
        try:
            lng = float(d0["x"])
            lat = float(d0["y"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "좌표 파싱에 실패했습니다."}

        addr = d0.get("address_name") or d0.get("road_address_name") or q
        return {
            "ok": True,
            "lat": lat,
            "lng": lng,
            "address_label": addr,
            "raw": d0,
            "geocode_source": "address",
        }

    if not keyword_first:
        kw = geocode_by_keyword_place(q, timeout=timeout)
        if kw.get("ok"):
            return kw

    return {
        "ok": False,
        "error": (
            "주소·장소 검색 결과가 없습니다. "
            "도로명 주소, 동 이름, 또는 대학·역 이름 등으로 다시 입력해 보세요."
        ),
    }


def search_keyword_near(
    lat: float,
    lng: float,
    keyword: str,
    radius: int = 3000,
    size: int = 10,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """키워드 장소 검색 (중심 + 반경). x=경도, y=위도."""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                KEYWORD_URL,
                headers=_headers(),
                params={
                    "query": keyword,
                    "x": lng,
                    "y": lat,
                    "radius": min(radius, 20000),
                    "size": min(size, 15),
                    "sort": "distance",
                },
            )
    except Exception as e:
        return {"ok": False, "error": str(e), "places": []}

    if r.status_code != 200:
        return {"ok": False, "error": f"키워드 API HTTP {r.status_code}", "places": []}

    data = r.json()
    docs = data.get("documents") or []
    places: list[dict[str, Any]] = []
    for d in docs:
        places.append(
            {
                "id": d.get("id"),
                "place_name": d.get("place_name", ""),
                "category_name": d.get("category_name", ""),
                "road_address_name": d.get("road_address_name", ""),
                "distance": d.get("distance", ""),
                "place_url": d.get("place_url", ""),
                "x": d.get("x"),
                "y": d.get("y"),
                "category_group_code": d.get("category_group_code", ""),
            }
        )
    return {"ok": True, "places": places}


def collect_study_spot_candidates(lat: float, lng: float, radius: int = 3000) -> dict[str, Any]:
    """카페·도서관 키워드 두 번 호출 후 id 기준 병합."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    errors: list[str] = []

    for kw in ("카페", "도서관"):
        res = search_keyword_near(lat, lng, kw, radius=radius)
        if not res.get("ok"):
            errors.append(res.get("error", "unknown"))
            continue
        for p in res.get("places") or []:
            pid = str(p.get("id") or p.get("place_name"))
            if pid in seen:
                continue
            seen.add(pid)
            merged.append(p)

    merged.sort(key=lambda p: float(p.get("distance") or 1e9))
    return {"ok": True, "places": merged, "errors": errors}
