from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select

from aviation_supply_console.api.schemas import (
    AircraftDetailOut,
    AircraftHistoryPointOut,
    AircraftMasterOut,
    AircraftStateOut,
    AirportSupplyOut,
    AirportVisitOut,
    MapAircraftOut,
    MapAirportOut,
    MapSnapshotOut,
    RouteCandidateOut,
)
from aviation_supply_console.core.config import get_settings
from aviation_supply_console.db.base import session_scope
from aviation_supply_console.models.entities import (
    AircraftMaster,
    AircraftStateCurrent,
    AirportSupplySnapshot,
    IngestionRun,
    PositionEvent,
)
from aviation_supply_console.services.airports import get_airport, haversine_nm, resolve_airport

router = APIRouter()
templates = Jinja2Templates(directory="src/aviation_supply_console/templates")

DISPLAY_CHARTER_CLASSES = ("light_jet", "midsize_jet", "heavy_jet", "turboprop", "rotorcraft")
ROUTE_CHARTER_CLASSES = ("light_jet", "midsize_jet", "heavy_jet", "turboprop")


def _latest_snapshot(session) -> datetime | None:
    return session.scalar(select(AircraftStateCurrent.snapshot_ts).order_by(AircraftStateCurrent.snapshot_ts.desc()).limit(1))


def _freshness_cutoff(latest_snapshot: datetime | None, *, minutes: int = 15) -> datetime:
    if latest_snapshot is None:
        return datetime.now(UTC) - timedelta(minutes=minutes)
    return latest_snapshot - timedelta(minutes=minutes)


def _fresh_charter_states_stmt(latest_snapshot: datetime | None, classes: tuple[str, ...]):
    cutoff = _freshness_cutoff(latest_snapshot)
    return select(AircraftStateCurrent).where(
        AircraftStateCurrent.snapshot_ts >= cutoff,
        AircraftStateCurrent.last_seen_at >= cutoff,
        AircraftStateCurrent.charter_relevant.is_(True),
        AircraftStateCurrent.aircraft_class.in_(classes),
    )


def _collector_status_payload(session) -> dict:
    settings = get_settings()
    live_provider = settings.live_provider.strip().lower()
    live_configured = live_provider == "opensky" or bool(settings.live_snapshot_url)
    latest_live_run = session.scalar(
        select(IngestionRun)
        .where(IngestionRun.source.in_(("adsbexchange_live_snapshot", "opensky_live_states")))
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )
    opensky_bbox = None
    if None not in (
        settings.opensky_lamin,
        settings.opensky_lomin,
        settings.opensky_lamax,
        settings.opensky_lomax,
    ):
        opensky_bbox = {
            "lamin": settings.opensky_lamin,
            "lomin": settings.opensky_lomin,
            "lamax": settings.opensky_lamax,
            "lomax": settings.opensky_lomax,
        }
    return {
        "live_configured": live_configured,
        "live_provider": live_provider,
        "live_snapshot_url": settings.live_snapshot_url,
        "poll_interval_seconds": settings.live_poll_interval_seconds,
        "auth_mode": (
            "oauth2_client_credentials"
            if settings.opensky_client_id and settings.opensky_client_secret
            else "anonymous"
        )
        if live_provider == "opensky"
        else ("header_token" if settings.live_auth_header_name and settings.live_auth_token else "none"),
        "opensky_states_url": settings.opensky_states_url if live_provider == "opensky" else None,
        "opensky_bbox": opensky_bbox if live_provider == "opensky" else None,
        "latest_live_run": {
            "status": latest_live_run.status,
            "started_at": latest_live_run.started_at,
            "completed_at": latest_live_run.completed_at,
            "records_written": latest_live_run.records_written,
            "source": latest_live_run.source,
        }
        if latest_live_run
        else None,
    }


@router.get("/", response_class=HTMLResponse)
def console_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={})


@router.get("/map", response_class=HTMLResponse)
def ops_map(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="map.html", context={})


@router.get("/aircraft/{hex_code}", response_class=HTMLResponse)
def aircraft_detail_page(request: Request, hex_code: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="aircraft_detail.html",
        context={"hex_code": hex_code.lower()},
    )


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/collector/status")
def collector_status() -> dict:
    with session_scope() as session:
        return _collector_status_payload(session)


@router.get("/api/ops/summary")
def ops_summary() -> dict:
    with session_scope() as session:
        latest_run = session.scalar(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1))
        latest_snapshot = _latest_snapshot(session)
        collector = _collector_status_payload(session)

        top_aircraft = []
        top_airports = []
        if latest_snapshot is not None:
            top_aircraft = list(
                session.scalars(
                    _fresh_charter_states_stmt(latest_snapshot, DISPLAY_CHARTER_CLASSES)
                    .order_by(
                        desc(AircraftStateCurrent.availability_score),
                        desc(AircraftStateCurrent.snapshot_ts),
                        desc(AircraftStateCurrent.idle_minutes),
                    )
                    .limit(15)
                ).all()
            )
            top_airports = list(
                session.scalars(
                    select(AirportSupplySnapshot)
                    .where(AirportSupplySnapshot.snapshot_ts == latest_snapshot)
                    .order_by(desc(AirportSupplySnapshot.charter_relevant_count), desc(AirportSupplySnapshot.total_aircraft))
                    .limit(10)
                ).all()
            )

    return {
        "latest_run": {
            "source": latest_run.source,
            "status": latest_run.status,
            "started_at": latest_run.started_at,
            "completed_at": latest_run.completed_at,
            "records_seen": latest_run.records_seen,
            "records_written": latest_run.records_written,
        }
        if latest_run
        else None,
        "latest_snapshot": latest_snapshot,
        "collector_status": collector,
        "top_aircraft": [AircraftStateOut.model_validate(item).model_dump(mode="json") for item in top_aircraft],
        "top_airports": [
            AirportSupplyOut(
                airport_icao=item.airport_icao,
                total_aircraft=item.total_aircraft,
                charter_relevant_count=item.charter_relevant_count,
                top_aircraft_hexes=item.top_aircraft_hexes,
                snapshot_ts=item.snapshot_ts,
            ).model_dump(mode="json")
            for item in top_airports
        ],
    }


@router.get("/api/aircraft/{hex_code}", response_model=AircraftStateOut)
def aircraft_lookup(hex_code: str) -> AircraftStateOut:
    with session_scope() as session:
        state = session.get(AircraftStateCurrent, hex_code.lower())
        if state is None:
            raise HTTPException(status_code=404, detail="Aircraft not found")
        return AircraftStateOut.model_validate(state)


@router.get("/api/aircraft/{hex_code}/history", response_model=AircraftDetailOut)
def aircraft_history(hex_code: str, limit: int = Query(48, ge=6, le=240)) -> AircraftDetailOut:
    normalized_hex = hex_code.lower()
    with session_scope() as session:
        state = session.get(AircraftStateCurrent, normalized_hex)
        if state is None:
            raise HTTPException(status_code=404, detail="Aircraft not found")

        master = session.get(AircraftMaster, normalized_hex)
        positions = list(
            session.scalars(
                select(PositionEvent)
                .where(PositionEvent.hex == normalized_hex)
                .order_by(PositionEvent.snapshot_ts.desc())
                .limit(limit)
            ).all()
        )
        positions.reverse()

        airport_rows = session.execute(
            select(
                PositionEvent.nearest_airport_icao,
                func.count(PositionEvent.id),
                func.max(PositionEvent.snapshot_ts),
            )
            .where(PositionEvent.hex == normalized_hex, PositionEvent.nearest_airport_icao.is_not(None))
            .group_by(PositionEvent.nearest_airport_icao)
            .order_by(func.max(PositionEvent.snapshot_ts).desc())
            .limit(8)
        ).all()

    return AircraftDetailOut(
        current=AircraftStateOut.model_validate(state),
        master=AircraftMasterOut(
            manufacturer=master.manufacturer if master else None,
            model=master.model if master else None,
            owner_operator=master.owner_operator if master else None,
        ),
        recent_positions=[
            AircraftHistoryPointOut(
                snapshot_ts=item.snapshot_ts,
                lat=item.lat,
                lon=item.lon,
                altitude_baro=item.altitude_baro,
                altitude_is_ground=item.altitude_is_ground,
                ground_speed=item.ground_speed,
                track=item.track,
                nearest_airport_icao=item.nearest_airport_icao,
            )
            for item in positions
        ],
        recent_airports=[
            AirportVisitOut(airport_icao=airport_icao, sample_count=sample_count, last_seen_at=last_seen_at)
            for airport_icao, sample_count, last_seen_at in airport_rows
            if airport_icao
        ],
    )


@router.get("/api/airports/{icao}/supply", response_model=AirportSupplyOut)
def airport_supply(icao: str) -> AirportSupplyOut:
    with session_scope() as session:
        snapshot = session.scalar(
            select(AirportSupplySnapshot)
            .where(AirportSupplySnapshot.airport_icao == icao.upper())
            .order_by(AirportSupplySnapshot.snapshot_ts.desc())
            .limit(1)
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Airport supply not found")

    return AirportSupplyOut(
        airport_icao=snapshot.airport_icao,
        total_aircraft=snapshot.total_aircraft,
        charter_relevant_count=snapshot.charter_relevant_count,
        top_aircraft_hexes=snapshot.top_aircraft_hexes,
        snapshot_ts=snapshot.snapshot_ts,
    )


@router.get("/api/map/aircraft", response_model=MapSnapshotOut)
def map_aircraft(
    limit: int = Query(300, ge=1, le=1000),
    classes: str | None = Query(None, description="Comma-separated aircraft classes"),
) -> MapSnapshotOut:
    selected_classes = tuple(
        sorted(
            {
                item.strip()
                for item in (classes or "").split(",")
                if item.strip() in DISPLAY_CHARTER_CLASSES
            }
        )
    ) or DISPLAY_CHARTER_CLASSES

    with session_scope() as session:
        latest_snapshot = _latest_snapshot(session)
        if latest_snapshot is None:
            return MapSnapshotOut(snapshot_ts=datetime.now(UTC), aircraft=[], airports=[])

        states = list(
            session.scalars(
                _fresh_charter_states_stmt(latest_snapshot, selected_classes)
                .where(AircraftStateCurrent.lat.is_not(None), AircraftStateCurrent.lon.is_not(None))
                .order_by(desc(AircraftStateCurrent.availability_score), desc(AircraftStateCurrent.snapshot_ts))
                .limit(limit)
            ).all()
        )
        airport_snapshots = list(
            session.scalars(
                select(AirportSupplySnapshot)
                .where(AirportSupplySnapshot.snapshot_ts == latest_snapshot)
                .order_by(desc(AirportSupplySnapshot.charter_relevant_count), desc(AirportSupplySnapshot.total_aircraft))
                .limit(16)
            ).all()
        )

    airports = []
    for snapshot in airport_snapshots:
        airport = get_airport(snapshot.airport_icao)
        if airport is None:
            continue
        airports.append(
            MapAirportOut(
                airport_icao=snapshot.airport_icao,
                name=airport.get("name"),
                lat=float(airport["lat"]),
                lon=float(airport["lon"]),
                charter_relevant_count=snapshot.charter_relevant_count,
                total_aircraft=snapshot.total_aircraft,
            )
        )

    return MapSnapshotOut(
        snapshot_ts=latest_snapshot,
        aircraft=[
            MapAircraftOut(
                hex=item.hex,
                reg=item.reg,
                flight=item.flight,
                icaotype=item.icaotype,
                aircraft_class=item.aircraft_class,
                lat=float(item.lat),
                lon=float(item.lon),
                nearest_airport_icao=item.nearest_airport_icao,
                availability_score=item.availability_score,
                availability_band=item.availability_band,
                snapshot_ts=item.snapshot_ts,
            )
            for item in states
            if item.lat is not None and item.lon is not None
        ],
        airports=airports,
    )


@router.get("/api/routes/candidates", response_model=list[RouteCandidateOut])
def route_candidates(
    origin: str = Query(..., min_length=3, max_length=4),
    destination: str = Query(..., min_length=3, max_length=4),
    limit: int = Query(20, ge=1, le=100),
) -> list[RouteCandidateOut]:
    origin_airport = resolve_airport(origin)
    destination_airport = resolve_airport(destination)
    if origin_airport is None or destination_airport is None:
        raise HTTPException(status_code=404, detail="Origin or destination airport not found in dataset")

    origin_icao = str(origin_airport["icao"]).upper()
    origin_lat = float(origin_airport["lat"])
    origin_lon = float(origin_airport["lon"])
    destination_lat = float(destination_airport["lat"])
    destination_lon = float(destination_airport["lon"])
    route_length_nm = haversine_nm(origin_lat, origin_lon, destination_lat, destination_lon)

    with session_scope() as session:
        latest_snapshot = _latest_snapshot(session)
        states = list(
            session.scalars(
                _fresh_charter_states_stmt(latest_snapshot, ROUTE_CHARTER_CLASSES)
                .where(AircraftStateCurrent.lat.is_not(None), AircraftStateCurrent.lon.is_not(None))
            ).all()
        )

    ranked = []
    class_range_nm = {
        "light_jet": 1800,
        "midsize_jet": 2500,
        "heavy_jet": 5000,
        "turboprop": 1600,
    }
    for state in states:
        if state.lat is None or state.lon is None:
            continue
        max_range_nm = class_range_nm.get(state.aircraft_class or "", 0)
        if max_range_nm and route_length_nm > max_range_nm:
            continue
        distance_from_origin = haversine_nm(origin_lat, origin_lon, state.lat, state.lon)
        score = state.availability_score - min(40, int(distance_from_origin // 25))
        if state.nearest_airport_icao == origin_icao:
            score += 20
        if route_length_nm >= 1200 and state.aircraft_class in {"heavy_jet", "midsize_jet"}:
            score += 8
        if state.idle_minutes and state.idle_minutes >= 120:
            score += 5
        ranked.append((score, distance_from_origin, state))

    ranked.sort(key=lambda row: (row[0], -row[2].availability_score), reverse=True)
    return [
        RouteCandidateOut(
            hex=item.hex,
            reg=item.reg,
            flight=item.flight,
            icaotype=item.icaotype,
            aircraft_class=item.aircraft_class,
            nearest_airport_icao=item.nearest_airport_icao,
            distance_from_origin_nm=round(distance_nm, 1),
            availability_score=item.availability_score,
            availability_band=item.availability_band,
            idle_minutes=item.idle_minutes,
        )
        for _, distance_nm, item in ranked[:limit]
    ]
