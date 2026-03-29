from __future__ import annotations

from dataclasses import dataclass


BUSINESS_JET_PREFIXES = {
    "light_jet": ("C25", "C510", "C525", "C550", "C560", "E50P", "HDJT", "LJ2", "LJ3", "LJ4", "LJ5"),
    "midsize_jet": ("BE40", "C56X", "C650", "C68A", "C680", "CL30", "E545", "E55P", "FA50", "LJ6"),
    "heavy_jet": ("C700", "C750", "CL35", "CL60", "FA7", "F2TH", "GALX", "GLEX", "GLF", "GL5", "GL6"),
    "turboprop": ("AT6", "BE20", "BE30", "BE9", "C208", "DHC6", "P180", "PC12", "TBM"),
    "rotorcraft": ("R44", "EC35", "A109", "B06", "H125"),
}

AIRLINER_PREFIXES = (
    "A19", "A20", "A21", "A318", "A319", "A320", "A321", "A330", "A332", "A333", "A338",
    "A339", "A340", "A350", "A359", "A388", "AT4", "AT7", "B37", "B38", "B39", "B3X",
    "B461", "B462", "B463", "B734", "B737", "B738", "B739", "B744", "B748", "B752", "B753",
    "B763", "B764", "B772", "B773", "B77L", "B77W", "B788", "B789", "BCS", "CRJ", "DH8",
    "E170", "E175", "E190", "E195", "E290", "E295", "E75", "MD11", "MD8", "SU95",
)

PISTON_PREFIXES = ("C150", "C152", "C162", "C172", "C177", "C182", "C206", "PA28", "PA32", "PA46", "SR20", "SR22")


@dataclass(frozen=True)
class AircraftClassification:
    aircraft_class: str | None
    charter_relevant: bool
    reason: str


def _type_code(raw_type: str | None) -> str:
    return (raw_type or "").strip().upper()


def classify_aircraft(
    *,
    type_code: str | None,
    reg: str | None,
    category: str | None,
    military: bool = False,
) -> AircraftClassification:
    t = _type_code(type_code)
    registration = (reg or "").strip().upper()

    if military:
        return AircraftClassification(None, False, "military")

    if any(t.startswith(prefix) for prefix in AIRLINER_PREFIXES):
        return AircraftClassification("airliner", False, "airliner_type")

    for aircraft_class, prefixes in BUSINESS_JET_PREFIXES.items():
        if any(t.startswith(prefix) for prefix in prefixes):
            return AircraftClassification(aircraft_class, True, "type_match")

    if category == "A7":
        return AircraftClassification("rotorcraft", True, "rotorcraft_category")

    if any(t.startswith(prefix) for prefix in PISTON_PREFIXES):
        return AircraftClassification("piston", False, "piston_type")

    if registration.startswith("N") and category == "A6":
        return AircraftClassification("high_performance_unknown", True, "us_high_performance")

    if category == "A5":
        return AircraftClassification("airliner", False, "heavy_category")

    return AircraftClassification(None, False, "unclassified")
