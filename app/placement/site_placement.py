"""Place the largest Plinth model footprint inside a parcel with setbacks."""

from __future__ import annotations

import json
import math
from typing import Any

from pyproj import Transformer
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.validation import make_valid

from app.models.plinth_models import BUILDING_SETBACK_FT, MODEL_SEPARATION_FT, PLINTH_MODELS
from app.placement.building_footprint import building_on_parcel

FT_TO_M = 0.3048
FIT_TOLERANCE_M = 0.01


def _utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _transform_coords(coords, transformer):
    if isinstance(coords[0], (int, float)):
        x, y = transformer.transform(coords[0], coords[1])
        return [x, y]
    return [_transform_coords(c, transformer) for c in coords]


def _to_local_meters(geom_wgs84, transformer_to_utm):
    projected = mapping(geom_wgs84)
    geom = shape(
        {
            "type": projected["type"],
            "coordinates": _transform_coords(projected["coordinates"], transformer_to_utm),
        }
    )
    if not geom.is_valid:
        geom = make_valid(geom)
    return geom


def _from_local_meters(geom_local, transformer_to_wgs84):
    projected = mapping(geom_local)
    return shape(
        {
            "type": projected["type"],
            "coordinates": _transform_coords(projected["coordinates"], transformer_to_wgs84),
        }
    )


def _as_geojson(geom) -> dict:
    return json.loads(json.dumps(mapping(geom)))


def _components(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return sorted((g for g in geom.geoms if not g.is_empty), key=lambda g: g.area, reverse=True)
    return [geom.convex_hull]


def _available_area(parcel_m, building_m) -> Polygon | MultiPolygon:
    parcel_m = parcel_m.buffer(0)
    if building_m is None or building_m.is_empty:
        return parcel_m
    setback_m = BUILDING_SETBACK_FT * FT_TO_M
    return parcel_m.difference(building_m.buffer(setback_m))


def _edge_angles_deg(poly: Polygon) -> set[float]:
    coords = list(poly.exterior.coords)
    out: set[float] = set()
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        out.add(round(ang, 3))
    return out


def _candidate_angles_deg(available) -> list[float]:
    base = {float(a) for a in range(0, 180, 5)}
    for poly in _components(available):
        base |= _edge_angles_deg(poly)
        mrr = poly.minimum_rotated_rectangle
        if mrr and not mrr.is_empty and mrr.geom_type == "Polygon":
            base |= _edge_angles_deg(mrr)
    return sorted(a % 180.0 for a in base)


def _grid_points(poly: Polygon, spacing_m: float, cap: int = 900) -> list[Point]:
    minx, miny, maxx, maxy = poly.bounds
    pts: list[Point] = [poly.representative_point(), poly.centroid]
    x = minx + spacing_m / 2.0
    while x <= maxx and len(pts) < cap:
        y = miny + spacing_m / 2.0
        while y <= maxy and len(pts) < cap:
            p = Point(x, y)
            if poly.covers(p):
                pts.append(p)
            y += spacing_m
        x += spacing_m
    return pts


def _base_rect(width_m: float, length_m: float) -> Polygon:
    return box(-width_m / 2.0, -length_m / 2.0, width_m / 2.0, length_m / 2.0)


def _candidate_rect(center: Point, rect_template: Polygon, angle_deg: float) -> Polygon:
    rotated = affinity.rotate(rect_template, angle_deg, origin=(0, 0), use_radians=False)
    return affinity.translate(rotated, xoff=center.x, yoff=center.y)


def _fits(fit_area, rect: Polygon) -> bool:
    if rect.is_empty:
        return False
    return fit_area.covers(rect)


def _clearance_score(available, rect: Polygon) -> float:
    # bigger is better: farther from forbidden area/boundary while still fitting.
    return rect.boundary.distance(available.boundary)


def _search_placement(available, width_ft: float, length_ft: float) -> tuple[Polygon, float] | None:
    if available.is_empty:
        return None

    width_m = width_ft * FT_TO_M
    length_m = length_ft * FT_TO_M
    spacing_m = max(0.75, min(width_m, length_m) / 3.5)
    fit_area = available.buffer(-FIT_TOLERANCE_M)
    if fit_area.is_empty:
        return None
    angles = _candidate_angles_deg(available)
    templates = [
        _base_rect(width_m, length_m),
        _base_rect(length_m, width_m),
    ]

    best_rect: Polygon | None = None
    best_angle = 0.0
    best_score = float("-inf")

    for poly in _components(available):
        points = _grid_points(poly, spacing_m=spacing_m, cap=450)
        for center in points:
            for angle in angles:
                for template in templates:
                    rect = _candidate_rect(center, template, angle)
                    if not _fits(fit_area, rect):
                        continue
                    score = _clearance_score(fit_area, rect)
                    if score > best_score:
                        best_rect, best_angle, best_score = rect, angle, score

    if best_rect is None:
        return None
    return best_rect, best_angle


def place_largest_model(
    parcel_geometry: dict,
    *,
    building_geometry: dict | None = None,
) -> dict[str, Any] | None:
    """
    Find the largest Plinth model that fits the parcel with required setbacks.
    """
    parcel_wgs = shape(parcel_geometry)
    if not parcel_wgs.is_valid:
        parcel_wgs = make_valid(parcel_wgs)
    if parcel_wgs.is_empty:
        return None

    centroid = parcel_wgs.centroid
    epsg = _utm_epsg(centroid.x, centroid.y)
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    to_wgs = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)

    parcel_m = _to_local_meters(parcel_wgs, to_utm)
    if building_geometry:
        print(f'building_geometry---------> {building_geometry}')
        building_wgs = shape(building_geometry)
    else:
        building_wgs = building_on_parcel(parcel_wgs)
        print(f'building_wgs---------> {building_wgs}')
    building_m = _to_local_meters(building_wgs, to_utm) if building_wgs is not None else None
    print(f'building_m---------> {building_m}')
    available = _available_area(parcel_m, building_m)
    print(f'available---------> {available}')
    if available.is_empty:
        return None

    building_geo = _as_geojson(building_wgs) if building_wgs is not None else None
    available_wgs = _from_local_meters(available, to_wgs)

    for model in PLINTH_MODELS:
        candidate = _search_placement(available, model.width_ft, model.length_ft)
        if candidate is None:
            continue
        rect_m, angle_deg = candidate
        rect_wgs = _from_local_meters(rect_m, to_wgs)
        return {
            "model_id": model.id,
            "model_name": model.name,
            "model_description": model.description,
            "footprint_label": model.footprint_label,
            "sqft": model.sqft,
            "bedrooms": model.bedrooms,
            "bathrooms": model.bathrooms,
            "kitchen": model.kitchen,
            "width_ft": model.width_ft,
            "length_ft": model.length_ft,
            "rotation_deg": round(float(angle_deg), 2),
            "geometry": _as_geojson(rect_wgs),
            "available_area_geometry": _as_geojson(available_wgs),
            "building_geometry": building_geo,
            "setbacks_ft": {
                "building": BUILDING_SETBACK_FT,
                "between_models": MODEL_SEPARATION_FT,
            },
        }

    return None

