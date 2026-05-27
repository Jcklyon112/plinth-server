"""
RentCast long-term rent AVM client.

Docs: https://developers.rentcast.io/reference/rent-estimate-long-term
"""

from __future__ import annotations

import os
from typing import Any

import httpx

RENTCAST_BASE = "https://api.rentcast.io/v1"
RENT_ESTIMATE_PATH = "/avm/rent/long-term"


class RentCastError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def get_rentcast_key() -> str | None:
    key = (os.environ.get("RENTCAST_API_KEY") or "").strip()
    if key:
        return key
    try:
        from app.config import settings

        key = (getattr(settings, "RENTCAST_API_KEY", None) or "").strip()
    except Exception:
        key = ""
    return key or None


def _headers() -> dict[str, str]:
    key = get_rentcast_key()
    if not key:
        raise RentCastError(
            "RentCast API key not configured. Set RENTCAST_API_KEY in backend/.env.",
            status_code=503,
        )
    return {"X-Api-Key": key, "Accept": "application/json"}


def fetch_monthly_rent(
    *,
    address: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    bedrooms: float,
    bathrooms: float,
    square_footage: int,
    property_type: str = "Single Family",
    timeout: float = 30,
) -> dict[str, Any]:
    """
    Return normalized rent estimate fields from RentCast.
    bedrooms may be fractional (e.g. 0.5); API expects a number — we round up for 0.5.
    """
    params: dict[str, str | int | float] = {
        "propertyType": property_type,
        "bathrooms": bathrooms,
        "squareFootage": square_footage,
        "lookupSubjectAttributes": "false",
        "compCount": 15,
    }

    bed_param = 0 if bedrooms < 1 else int(round(bedrooms))
    params["bedrooms"] = bed_param

    if address:
        params["address"] = address
    elif lat is not None and lon is not None:
        params["latitude"] = lat
        params["longitude"] = lon
    else:
        raise RentCastError("address or lat/lon required for rent estimate")

    url = f"{RENTCAST_BASE}{RENT_ESTIMATE_PATH}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params, headers=_headers())

    try:
        data = resp.json()
    except Exception:
        data = {}

    if resp.status_code >= 400:
        msg = (
            (data.get("message") if isinstance(data, dict) else None)
            or (data.get("error") if isinstance(data, dict) else None)
            or resp.text[:300]
            or f"HTTP {resp.status_code}"
        )
        raise RentCastError(str(msg), status_code=resp.status_code)

    if not isinstance(data, dict):
        raise RentCastError("Unexpected RentCast response format")

    rent = data.get("rent")
    if rent is None:
        raise RentCastError("RentCast response missing rent estimate")

    return {
        "monthly_rent_usd": round(float(rent)),
        "rent_range_low_usd": _optional_int(data.get("rentRangeLow")),
        "rent_range_high_usd": _optional_int(data.get("rentRangeHigh")),
        "property_type": property_type,
        "bedrooms": bed_param,
        "bathrooms": bathrooms,
        "square_footage": square_footage,
    }


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None
