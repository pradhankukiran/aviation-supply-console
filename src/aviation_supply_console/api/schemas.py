from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AircraftStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hex: str
    snapshot_ts: datetime
    flight: str | None
    reg: str | None
    icaotype: str | None
    aircraft_class: str | None
    charter_relevant: bool
    relevance_reason: str | None
    lat: float | None
    lon: float | None
    altitude_baro: float | None
    altitude_is_ground: bool
    ground_speed: float | None
    nearest_airport_icao: str | None
    last_airport_icao: str | None
    idle_minutes: int | None
    activity_24h: int
    activity_72h: int
    availability_score: int
    availability_band: str


class AirportSupplyOut(BaseModel):
    airport_icao: str
    total_aircraft: int
    charter_relevant_count: int
    top_aircraft_hexes: list[str]
    snapshot_ts: datetime


class RouteCandidateOut(BaseModel):
    hex: str
    reg: str | None
    flight: str | None
    icaotype: str | None
    aircraft_class: str | None
    nearest_airport_icao: str | None
    distance_from_origin_nm: float | None
    availability_score: int
    availability_band: str
    idle_minutes: int | None


class AircraftMasterOut(BaseModel):
    manufacturer: str | None
    model: str | None
    owner_operator: str | None


class AircraftHistoryPointOut(BaseModel):
    snapshot_ts: datetime
    lat: float | None
    lon: float | None
    altitude_baro: float | None
    altitude_is_ground: bool
    ground_speed: float | None
    track: float | None
    nearest_airport_icao: str | None


class AirportVisitOut(BaseModel):
    airport_icao: str
    sample_count: int
    last_seen_at: datetime


class AircraftDetailOut(BaseModel):
    current: AircraftStateOut
    master: AircraftMasterOut
    recent_positions: list[AircraftHistoryPointOut]
    recent_airports: list[AirportVisitOut]


class MapAircraftOut(BaseModel):
    hex: str
    reg: str | None
    flight: str | None
    icaotype: str | None
    aircraft_class: str | None
    lat: float
    lon: float
    nearest_airport_icao: str | None
    availability_score: int
    availability_band: str
    snapshot_ts: datetime


class MapAirportOut(BaseModel):
    airport_icao: str
    name: str | None
    lat: float
    lon: float
    charter_relevant_count: int
    total_aircraft: int


class MapSnapshotOut(BaseModel):
    snapshot_ts: datetime
    aircraft: list[MapAircraftOut]
    airports: list[MapAirportOut]
