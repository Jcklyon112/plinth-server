"""Plinth single-family ADU model catalog for site placement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlinthModelSpec:
    id: int
    name: str
    width_ft: float
    length_ft: float
    sqft: int
    bedrooms: float
    bathrooms: float
    kitchen: str
    description: str

    @property
    def footprint_label(self) -> str:
        w = int(self.width_ft) if self.width_ft == int(self.width_ft) else self.width_ft
        l = int(self.length_ft) if self.length_ft == int(self.length_ft) else self.length_ft
        return f"{w}×{l} ft"


# Largest first for placement (try Model 3, then 2, then 1).
PLINTH_MODELS: tuple[PlinthModelSpec, ...] = (
    PlinthModelSpec(
        id=3,
        name="Model 3",
        width_ft=16,
        length_ft=63,
        sqft=900,
        bedrooms=2,
        bathrooms=2,
        kitchen="full kitchen",
        description="2 bed, 2 bath, full kitchen",
    ),
    PlinthModelSpec(
        id=2,
        name="Model 2",
        width_ft=16,
        length_ft=44,
        sqft=700,
        bedrooms=1,
        bathrooms=1,
        kitchen="full kitchen",
        description="1 bed, 1 bath, full kitchen",
    ),
    PlinthModelSpec(
        id=1,
        name="Model 1",
        width_ft=16,
        length_ft=24,
        sqft=400,
        bedrooms=0.5,
        bathrooms=1,
        kitchen="kitchenette",
        description="1/2 bed, 1 bath, kitchenette",
    ),
)

BUILDING_SETBACK_FT = 10.0
MODEL_SEPARATION_FT = 15.0
