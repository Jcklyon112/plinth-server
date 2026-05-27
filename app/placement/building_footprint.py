"""Fetch or estimate main-building footprints for setback calculations."""

from __future__ import annotations

import httpx
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _poly_to_overpass_latlon(geom) -> str:
    """Overpass poly string: 'lat lon lat lon ...' from a Shapely polygon in WGS84 (x=lon, y=lat)."""
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    if geom.geom_type != "Polygon":
        geom = geom.convex_hull
    coords = list(geom.exterior.coords)
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return " ".join(f"{lat} {lon}" for lon, lat in coords)


def fetch_buildings_wgs84(parcel_geom_wgs84) -> MultiPolygon | Polygon | None:
    """
    Query OSM building ways inside the parcel polygon.
    Returns a union geometry in WGS84 or None if none found / request failed.
    """
    if parcel_geom_wgs84 is None or parcel_geom_wgs84.is_empty:
        return None

    poly_str = _poly_to_overpass_latlon(parcel_geom_wgs84)
    query = f"""
    [out:json][timeout:25];
    (
      way["building"](poly:"{poly_str}");
      relation["building"]["type"="multipolygon"](poly:"{poly_str}");
    );
    out geom;
    """
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(_OVERPASS_URL, data={"data": query})
        if resp.status_code >= 400:
            return None
        data = resp.json()
    except Exception:
        return None

    geoms = []
    for el in data.get("elements") or []:
        g = _element_to_polygon(el)
        if g is not None and not g.is_empty:
            geoms.append(g)

    if not geoms:
        return None

    merged = unary_union(geoms)
    if merged.is_empty:
        return None
    if not merged.is_valid:
        merged = make_valid(merged)
    return merged


def _element_to_polygon(el: dict) -> Polygon | None:
    tags = el.get("tags") or {}
    if not tags.get("building"):
        return None

    if el.get("type") == "way" and el.get("geometry"):
        coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
        if len(coords) < 3:
            return None
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        try:
            return Polygon(coords)
        except Exception:
            return None

    if el.get("type") == "relation" and el.get("members"):
        outer_rings: list[list[tuple[float, float]]] = []
        for mem in el["members"]:
            if mem.get("role") != "outer" or mem.get("type") != "way":
                continue
            geom = mem.get("geometry")
            if not geom:
                continue
            ring = [(pt["lon"], pt["lat"]) for pt in geom]
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                outer_rings.append(ring)
        if not outer_rings:
            return None
        try:
            polys = [Polygon(r) for r in outer_rings if len(r) >= 4]
            return unary_union(polys) if polys else None
        except Exception:
            return None

    return None


def estimate_building_wgs84(parcel_geom_wgs84) -> Polygon | None:
    """
    Heuristic when OSM has no building: ~28% of parcel area, capped footprint,
    centered on the parcel interior point farthest from the boundary.
    """
    if parcel_geom_wgs84 is None or parcel_geom_wgs84.is_empty:
        return None

    from shapely.ops import polylabel

    geom = parcel_geom_wgs84
    if not geom.is_valid:
        geom = make_valid(geom)

    try:
        from pyproj import Geod

        geod = Geod(ellps="WGS84")
        area_m2, _ = geod.geometry_area_perimeter(geom)
        parcel_sqft = abs(area_m2) * 10.763910416709722
    except Exception:
        parcel_sqft = 8000.0

    target_sqft = min(max(parcel_sqft * 0.28, 900), 2800)
    side_ft = (target_sqft**0.5) * 0.85
    side_deg = side_ft / 364000.0

    try:
        center = polylabel(geom, tolerance=1e-9)
    except Exception:
        center = geom.representative_point()

    half = side_deg / 2
    return Polygon(
        [
            (center.x - half, center.y - half),
            (center.x + half, center.y - half),
            (center.x + half, center.y + half),
            (center.x - half, center.y + half),
            (center.x - half, center.y - half),
        ]
    )


def building_on_parcel(parcel_geom_wgs84) -> Polygon | MultiPolygon | None:
    """OSM buildings when available; otherwise a centroid-based estimate."""
    osm = fetch_buildings_wgs84(parcel_geom_wgs84)
    if osm is not None and not osm.is_empty:
        clipped = osm.intersection(parcel_geom_wgs84)
        if not clipped.is_empty:
            return clipped
    return estimate_building_wgs84(parcel_geom_wgs84)
