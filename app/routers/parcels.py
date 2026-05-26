from fastapi import APIRouter, HTTPException, Body

router = APIRouter()


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

    return {
        "status": "found",
        "parcel": {
            "address": result["address"],
            "lot_area_sqft": result["lot_area_sqft"],
        },
        "geometry": result["geometry"],
        "source": "rapidapi",
        "message": "Parcel loaded from RapidAPI Property Lines.",
    }


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
