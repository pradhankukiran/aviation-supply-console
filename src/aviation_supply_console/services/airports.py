from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from math import floor
from math import asin, cos, radians, sin, sqrt

import airportsdata

from aviation_supply_console.core.config import get_settings


@dataclass(frozen=True)
class AirportMatch:
    icao: str
    name: str
    distance_nm: float
    lat: float
    lon: float


@dataclass(frozen=True)
class AirportIndex:
    airports: dict[str, dict]
    grid: dict[tuple[int, int], list[tuple[str, dict]]]
    by_iata: dict[str, dict]
    by_lid: dict[str, dict]


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_nm * asin(sqrt(a))


@lru_cache
def load_airports() -> dict[str, dict]:
    settings = get_settings()
    airports = airportsdata.load("ICAO")
    return {
        code: airport
        for code, airport in airports.items()
        if airport.get("country") == settings.default_airport_country
        and airport.get("lat")
        and airport.get("lon")
    }


@lru_cache
def load_airport_index() -> AirportIndex:
    airports = load_airports()
    grid: dict[tuple[int, int], list[tuple[str, dict]]] = defaultdict(list)
    by_iata: dict[str, dict] = {}
    by_lid: dict[str, dict] = {}
    for code, airport in airports.items():
        key = (floor(float(airport["lat"])), floor(float(airport["lon"])))
        grid[key].append((code, airport))
        if airport.get("iata"):
            by_iata[str(airport["iata"]).upper()] = airport
        if airport.get("lid"):
            by_lid[str(airport["lid"]).upper()] = airport
    return AirportIndex(airports=airports, grid=dict(grid), by_iata=by_iata, by_lid=by_lid)


def get_airport(icao: str) -> dict | None:
    return load_airport_index().airports.get(icao.upper())


def resolve_airport(code: str) -> dict | None:
    normalized = code.upper()
    index = load_airport_index()
    return (
        index.airports.get(normalized)
        or index.by_iata.get(normalized)
        or index.by_lid.get(normalized)
    )


def nearest_airport(lat: float | None, lon: float | None) -> AirportMatch | None:
    if lat is None or lon is None:
        return None

    settings = get_settings()
    index = load_airport_index()
    lat_bucket = floor(lat)
    lon_bucket = floor(lon)

    best: AirportMatch | None = None
    candidates: list[tuple[str, dict]] = []
    for lat_offset in range(-2, 3):
        for lon_offset in range(-2, 3):
            candidates.extend(index.grid.get((lat_bucket + lat_offset, lon_bucket + lon_offset), []))

    for icao, airport in candidates:
        distance = haversine_nm(lat, lon, float(airport["lat"]), float(airport["lon"]))
        if best is None or distance < best.distance_nm:
            best = AirportMatch(
                icao=icao,
                name=str(airport.get("name", icao)),
                distance_nm=distance,
                lat=float(airport["lat"]),
                lon=float(airport["lon"]),
            )

    if best and best.distance_nm <= settings.airport_match_radius_nm:
        return best
    return None
