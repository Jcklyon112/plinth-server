"""
RapidAPI Property Lines client for live coordinate parcel lookup.

Endpoint: https://property-lines.p.rapidapi.com/get_us_radius_property_boundaries
"""

from __future__ import annotations

import os

import httpx
from shapely.geometry import Point, shape

RAPIDAPI_HOST = "property-lines.p.rapidapi.com"
RAPIDAPI_BASE = f"https://{RAPIDAPI_HOST}"
BOUNDARY_PATH = "/get_us_radius_property_boundaries"

_BROWSER_HEADERS = {
    "User-Agent": "Plinth-SIP/1.0",
    "Accept": "application/json",
}


class RapidAPIError(Exception):
    """Property Lines API returned an error response."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def get_rapidapi_key() -> str | None:
    """API key from X-RAPIDAPI-KEY in env or settings."""
    key = (os.environ.get("X-RAPIDAPI-KEY") or "").strip()
    if key:
        return key
    try:
        from app.config import settings

        key = (getattr(settings, "X_RAPIDAPI_KEY", None) or "").strip()
    except Exception:
        key = ""
    return key or None


def _rapidapi_headers() -> dict[str, str]:
    key = get_rapidapi_key()
    if not key:
        raise RapidAPIError(
            "RapidAPI key not configured. Set X-RAPIDAPI-KEY in backend/.env.",
            status_code=503,
        )
    return {
        **_BROWSER_HEADERS,
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }


def _extract_features(data: dict) -> list[dict]:
    if data.get("error"):
        err = data["error"]
        detail = err.get("detail") or err.get("title") or "Property Lines API error"
        raise RapidAPIError(str(detail))

    features = data.get("features")
    if isinstance(features, list):
        return features
    return []


def fetch_boundary_at_point(lat: float, lon: float, *, timeout: float = 45) -> list[dict]:
    """Return parcel boundary GeoJSON features at a WGS84 point."""
    url = f"{RAPIDAPI_BASE}{BOUNDARY_PATH}"
    params = {"lat": lat, "lon": lon, "radius": 50}

    with httpx.Client(timeout=timeout, follow_redirects=True, http2=False) as client:
        resp = client.get(url, params=params, headers=_rapidapi_headers())

    try:
        data = resp.json()
    except Exception:
        data = {}

    if resp.status_code >= 400:
        msg = (
            (data.get("error", {}).get("detail") if isinstance(data, dict) else None)
            or resp.text[:300]
            or f"HTTP {resp.status_code}"
        )
        raise RapidAPIError(msg, status_code=resp.status_code)

    if not isinstance(data, dict):
        raise RapidAPIError("Unexpected Property Lines response format", status_code=resp.status_code)
    return _extract_features(data)


def _coords_nonempty(geom: dict) -> bool:
    """True if GeoJSON coordinates contain at least one numeric value."""
    coords = geom.get("coordinates")
    if coords is None:
        return False
    stack: list = [coords]
    while stack:
        item = stack.pop()
        if isinstance(item, (int, float)):
            return True
        if isinstance(item, (list, tuple)):
            stack.extend(item)
    return False


def _geometry_area_sqft(geom_dict: dict) -> float | None:
    """Geodesic lot area in sqft from a WGS84 GeoJSON geometry (lon, lat order)."""
    if not isinstance(geom_dict, dict) or not _coords_nonempty(geom_dict):
        return None

    try:
        from pyproj import Geod
        from shapely.validation import make_valid

        geom = shape(geom_dict)
        if geom.is_empty:
            return None

        minx, miny, maxx, maxy = geom.bounds
        if not (
            -180 <= minx <= 180
            and -180 <= maxx <= 180
            and -90 <= miny <= 90
            and -90 <= maxy <= 90
        ):
            return None

        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.is_empty:
            return None

        geod = Geod(ellps="WGS84")
        area_m2, _ = geod.geometry_area_perimeter(geom)
        sqft = abs(area_m2) * 10.763910416709722
        if sqft <= 0:
            return None
        return round(sqft, 2)
    except Exception:
        return None


def normalize_rapidapi_feature(
    feature: dict,
    *,
    address_fallback: str | None = None,
) -> dict:
    """Map a Property Lines GeoJSON feature to address and lot area."""
    props = feature.get("properties") or {}
    geom_raw = feature.get("geometry")
    geom = geom_raw if isinstance(geom_raw, dict) and _coords_nonempty(geom_raw) else None

    address = (
        props.get("address")
        or props.get("situs")
        or props.get("formatted_address")
        or address_fallback
    )
    lot_area_sqft = _geometry_area_sqft(geom) if geom else None
    return {
        "address": address,
        "lot_area_sqft": lot_area_sqft,
        "geometry": geom,
    }


def _closest_feature(features: list[dict], lon: float, lat: float) -> dict | None:
    pt = Point(lon, lat)
    best, best_dist = None, float("inf")
    for feat in features:
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        try:
            dist = pt.distance(shape(geom_dict).centroid)
            if dist < best_dist:
                best_dist, best = dist, feat
        except Exception:
            continue
    return best or (features[0] if features else None)


def lookup_parcel_at_coordinates(
    lat: float,
    lon: float,
    *,
    address_hint: str | None = None,
) -> dict | None:
    """Fetch parcel boundary at (lon, lat) from RapidAPI Property Lines."""
    features = fetch_boundary_at_point(lat, lon)
    feature = _closest_feature(features, lon, lat)
    if not feature:
        return None

    result = normalize_rapidapi_feature(feature, address_fallback=address_hint)
    if not result.get("geometry"):
        return None
    return result
