"""Kakao Local API — 주소 검색(지오코딩) + 키워드 장소 검색."""

from __future__ import annotations

import os
from typing import Any

import httpx

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def _headers() -> dict[str, str]:
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        raise RuntimeError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")
    return {"Authorization": f"KakaoAK {key}"}


def geocode_by_keyword_place(query: str, timeout: float = 10.0) -> dict[str, Any]:
    """
    건물·캠퍼스·역 등 **장소 키워드** → 좌표 (키워드 검색 API, 중심 좌표 불필요).
    예: 부산대, 서울역, 장전역 — 주소 검색(address.json)이 비어 있을 때 사용.
    """
    q = query.strip()
    if not q:
        return {"ok": False, "error": "검색어가 비어 있습니다."}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                KEYWORD_URL,
                headers=_headers(),
                params={
                    "query": q,
                    "size": 5,
                    "sort": "accuracy",
                },
            )
    except Exception as e:
        return {"ok": False, "error": f"네트워크 오류: {e}"}

    if r.status_code == 401:
        return {"ok": False, "error": "카카오 API 키가 거부되었습니다."}
    if r.status_code != 200:
        return {"ok": False, "error": f"키워드 API HTTP {r.status_code}: {r.text[:200]}"}

    data = r.json()
    docs = data.get("documents") or []
    if not docs:
        return {"ok": False, "error": "키워드 검색 결과가 없습니다."}

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
    1) 주소 검색 API (도로명·지번에 강함)
    2) 결과가 없으면 키워드 장소 검색 (부산대, ○○역 등)
    """
    q = query.strip()
    if not q:
        return {"ok": False, "error": "주소·지명이 비어 있습니다."}
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

    # No jibun/road hit — try POI / campus / station names
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
