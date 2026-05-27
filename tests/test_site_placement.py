"""Placement geometry tests (no external APIs)."""

from pyproj import Transformer
from shapely.geometry import shape

from app.models.plinth_models import BUILDING_SETBACK_FT
from app.placement.site_placement import place_largest_model


def _square_parcel_ft(side_ft: float):
    lon, lat = -71.43, 42.48
    d = side_ft / 364000.0
    return {
        "type": "Polygon",
        "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]],
    }


def _project_to_utm(geom_dict):
    geom = shape(geom_dict)
    centroid = geom.centroid
    zone = int((centroid.x + 180) / 6) + 1
    epsg = (32600 if centroid.y >= 0 else 32700) + zone
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return shape(
        {
            "type": geom.geom_type,
            "coordinates": _transform_coords(geom_dict["coordinates"], to_utm),
        }
    )


def _transform_coords(coords, transformer):
    if isinstance(coords[0], (int, float)):
        x, y = transformer.transform(coords[0], coords[1])
        return [x, y]
    return [_transform_coords(c, transformer) for c in coords]


def test_places_largest_model_when_lot_supports_it():
    geom = _square_parcel_ft(230)
    lon, lat = -71.43, 42.48
    bd = 22 / 364000.0
    building = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon + 0.00006, lat + 0.00006],
                [lon + 0.00006 + bd, lat + 0.00006],
                [lon + 0.00006 + bd, lat + 0.00006 + bd],
                [lon + 0.00006, lat + 0.00006 + bd],
                [lon + 0.00006, lat + 0.00006],
            ]
        ],
    }
    placement = place_largest_model(geom, building_geometry=building)
    assert placement is not None
    assert placement["model_id"] == 3
    assert placement["geometry"]["type"] == "Polygon"


def test_respects_building_setback():
    geom = _square_parcel_ft(200)
    lon, lat = -71.43, 42.48
    bd = 30 / 364000.0
    building = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon + 0.00009, lat + 0.00009],
                [lon + 0.00009 + bd, lat + 0.00009],
                [lon + 0.00009 + bd, lat + 0.00009 + bd],
                [lon + 0.00009, lat + 0.00009 + bd],
                [lon + 0.00009, lat + 0.00009],
            ]
        ],
    }
    placement = place_largest_model(geom, building_geometry=building)
    assert placement is not None

    placement_m = _project_to_utm(placement["geometry"])
    building_m = _project_to_utm(building)
    setback_m = BUILDING_SETBACK_FT * 0.3048
    assert building_m.buffer(setback_m - 0.02).disjoint(placement_m)
