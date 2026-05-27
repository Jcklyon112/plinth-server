from fastapi import APIRouter, HTTPException, Body

from app.placement.site_placement import place_largest_model

router = APIRouter()


def _enrich_parcel_with_placement_and_rent(
    result: dict,
    *,
    lat: float,
    lon: float,
) -> dict:
    """Attach largest-model placement footprint and RentCast monthly rent."""
    geom = result.get("geometry")
    if not geom:
        return result

    try:
        placement = place_largest_model(geom)
    except Exception as exc:
        print(f"[search] placement failed: {exc}")
        placement = None
    print(f'placement---------> {placement}')
    if not placement:
        result["placement"] = None
        result["rent"] = None
        return result

    result["placement"] = placement
    from app.agents.rentcast_client import RentCastError, fetch_monthly_rent, get_rentcast_key

    if not get_rentcast_key():
        result["rent"] = {
            "status": "unconfigured",
            "message": "RentCast API key not configured. Set RENTCAST_API_KEY in backend/.env.",
        }
        return result

    address = (result.get("parcel") or {}).get("address") or ""
    try:
        rent = fetch_monthly_rent(
            address=address or None,
            lat=lat if not address else None,
            lon=lon if not address else None,
            bedrooms=float(placement["bedrooms"]),
            bathrooms=float(placement["bathrooms"]),
            square_footage=int(placement["sqft"]),
        )
        result["rent"] = {"status": "ok", **rent}
    except RentCastError as exc:
        print(f"[search] RentCast failed: {exc}")
        result["rent"] = {"status": "error", "message": str(exc)}
    except Exception as exc:
        print(f"[search] RentCast failed: {type(exc).__name__}: {exc}")
        result["rent"] = {"status": "error", "message": str(exc)}

    return result


def _rapidapi_search_response(
    lat: float,
    lon: float,
    *,
    address_hint: str | None = None,
) -> dict | None:
    from app.agents.rapidapi_client import (
        RapidAPIError,
        get_rapidapi_key,
        lookup_parcel_at_coordinates,
    )

    if not get_rapidapi_key():
        return {
            "status": "no_match",
            "message": (
                "RapidAPI key not configured. "
                "Set X-RAPIDAPI-KEY in backend/.env."
            ),
        }

    try:
        result = lookup_parcel_at_coordinates(
            lat,
            lon,
            address_hint=address_hint,
        )
    except RapidAPIError as exc:
        print(f"[search] RapidAPI lookup failed: {exc}")
        return {"status": "no_match", "message": str(exc)}
    except Exception as exc:
        print(f"[search] RapidAPI lookup failed: {type(exc).__name__}: {exc}")
        err_name = type(exc).__name__
        if "ConnectError" in err_name or "getaddrinfo" in str(exc).lower():
            msg = (
                "Could not reach RapidAPI (network/DNS). "
                "Check your internet connection and try again."
            )
        else:
            msg = f"Parcel lookup failed: {exc}"
        return {"status": "no_match", "message": msg}

    if not result:
        return None

    payload = {
        "status": "found",
        "parcel": {
            "address": result["address"],
            "lot_area_sqft": result["lot_area_sqft"],
        },
        "geometry": result["geometry"],
        "source": "rapidapi",
        "message": "Parcel loaded from RapidAPI Property Lines.",
    }
    return _enrich_parcel_with_placement_and_rent(payload, lat=lat, lon=lon)


@router.post("/search")
def search_parcel(data: dict = Body(...)):
    """
    Search for a parcel at Mapbox-selected coordinates via RapidAPI Property Lines.
    Body: {"address": "...", "lat": 40.7, "lon": -73.9}
    """
    address = data.get("address", "").strip()
    if not address:
        raise HTTPException(status_code=400, detail="'address' field is required")

    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="lat and lon are required — select an address from the suggestions dropdown.",
        )

    rapidapi = _rapidapi_search_response(lat, lon, address_hint=address)
    if rapidapi:
        return rapidapi

    return {
        "status": "no_match",
        "message": "No parcel found for this location in Property Lines.",
    }
