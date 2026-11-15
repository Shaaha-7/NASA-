"""Typed request models (Pydantic). Coordinates are [lon, lat], degrees, east-positive, Mars 2000 sphere."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LonLat(BaseModel):
    lon: float = Field(..., description="Longitude, degrees east (-180..360)")
    lat: float = Field(..., ge=-90, le=90, description="Planetocentric latitude, degrees")
    name: str | None = None

    @field_validator("lon")
    @classmethod
    def lon_range(cls, v):
        if not -180 <= v <= 360:
            raise ValueError("lon must be in -180..360 (east positive)")
        return v


class EvaOverrides(BaseModel):
    max_slope_deg: float | None = None
    caution_slope_deg: float | None = None
    flat_speed_kmh: float | None = None
    eva_hours: float | None = None
    reserve_fraction: float | None = None
    load_kg: float | None = None
    roughness_max_m: float | None = None
    roughness_caution_m: float | None = None
    round_trip: bool | None = None
    crew_size: int | None = Field(None, ge=1, le=4)
    shared_load_kg: float | None = Field(None, ge=0, le=400)


class RouteRequest(BaseModel):
    region_id: str
    start: LonLat
    destination: LonLat
    stops: list[LonLat] = Field(default_factory=list, max_length=8, description="Science stops visited in order")
    profile: Literal["fastest", "gentlest", "shortest"] = "fastest"
    optimise_stop_order: bool = Field(False, description="Reorder the stops to minimise the profile's cost")
    eva: EvaOverrides = Field(default_factory=EvaOverrides)


class ReachabilityRequest(BaseModel):
    region_id: str
    start: LonLat = Field(..., description="Habitat or EVA start point")
    eva: EvaOverrides = Field(default_factory=EvaOverrides)
    include_science_sites: bool = Field(True, description="Report which curated science stops are in range")


class CompareRequest(BaseModel):
    region_id: str
    start: LonLat
    destination: LonLat
    stops: list[LonLat] = Field(default_factory=list, max_length=8)
    profiles: list[Literal["fastest", "gentlest", "shortest"]] = ["fastest", "gentlest", "shortest"]
    eva: EvaOverrides = Field(default_factory=EvaOverrides)


class MissionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    region_id: str
    route: dict
    science_stops: list[dict] = Field(default_factory=list)
    notes: str | None = Field(None, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    region_id: str | None = None
    lon: float | None = None
    lat: float | None = None


class RoverParams(BaseModel):
    rover_type: Literal["pressurized", "unpressurized"] = Field(
        "pressurized", description="pressurized: crew rides in a cabin (NASA SEV concept); unpressurized: crew rides in suits (Apollo LRV / SEV Chariot style)")
    speed_kmh: float = Field(10.0, ge=1, le=20, description="Driving speed on flat smooth ground (NASA SEV concept: about 10 km/h)")
    stop_minutes: float = Field(30.0, ge=0, le=240, description="EVA work time at each stop (team assumption)")
    suitport_minutes: float = Field(10.0, ge=0, le=60, description="Suit-up and exit through the suitport, each way (NASA SEV concept: under 10 min)")


class RoverRouteRequest(RouteRequest):
    rover: RoverParams = Field(default_factory=RoverParams)
