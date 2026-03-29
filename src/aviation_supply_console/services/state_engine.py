from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.orm import Session

from aviation_supply_console.models.entities import (
    AircraftStateCurrent,
    AirportSupplySnapshot,
    PositionEvent,
)


def _availability_band(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def _availability_score(event: PositionEvent, idle_minutes: int | None, activity_24h: int) -> int:
    score = 20
    if event.charter_relevant:
        score += 30
    if event.altitude_is_ground and event.nearest_airport_icao:
        score += 20
    if idle_minutes is not None:
        if idle_minutes >= 24 * 60:
            score += 20
        elif idle_minutes >= 4 * 60:
            score += 10
    if activity_24h >= 12:
        score -= 20
    elif activity_24h >= 5:
        score -= 10
    if event.source_type == "mlat":
        score -= 5
    return max(0, min(100, score))


def _last_seen_at(snapshot_ts: datetime, seen_seconds: float | None) -> datetime:
    if not seen_seconds:
        return snapshot_ts
    return snapshot_ts - timedelta(seconds=seen_seconds)


def refresh_current_state(session: Session, snapshot_ts: datetime) -> None:
    snapshot_events = list(
        session.scalars(select(PositionEvent).where(PositionEvent.snapshot_ts == snapshot_ts)).all()
    )
    if not snapshot_events:
        return

    hexes = [event.hex for event in snapshot_events]
    window_24_start = snapshot_ts - timedelta(hours=24)
    window_72_start = snapshot_ts - timedelta(hours=72)

    activity_24h = {
        hex_code: count
        for hex_code, count in session.execute(
            select(PositionEvent.hex, func.count(PositionEvent.id))
            .where(
                PositionEvent.hex.in_(hexes),
                PositionEvent.snapshot_ts >= window_24_start,
                PositionEvent.snapshot_ts <= snapshot_ts,
            )
            .group_by(PositionEvent.hex)
        ).all()
    }
    activity_72h = {
        hex_code: count
        for hex_code, count in session.execute(
            select(PositionEvent.hex, func.count(PositionEvent.id))
            .where(
                PositionEvent.hex.in_(hexes),
                PositionEvent.snapshot_ts >= window_72_start,
                PositionEvent.snapshot_ts <= snapshot_ts,
            )
            .group_by(PositionEvent.hex)
        ).all()
    }

    ground_hexes = [event.hex for event in snapshot_events if event.altitude_is_ground and event.nearest_airport_icao]
    prior_active = {
        hex_code: ts
        for hex_code, ts in session.execute(
            select(PositionEvent.hex, func.max(PositionEvent.snapshot_ts))
            .where(
                PositionEvent.hex.in_(ground_hexes),
                PositionEvent.snapshot_ts < snapshot_ts,
                (PositionEvent.altitude_is_ground.is_(False))
                | ((PositionEvent.ground_speed.is_not(None)) & (PositionEvent.ground_speed > 80)),
            )
            .group_by(PositionEvent.hex)
        ).all()
    } if ground_hexes else {}

    last_airport_ts = {
        hex_code: ts
        for hex_code, ts in session.execute(
            select(PositionEvent.hex, func.max(PositionEvent.snapshot_ts))
            .where(
                PositionEvent.hex.in_(hexes),
                PositionEvent.snapshot_ts <= snapshot_ts,
                PositionEvent.nearest_airport_icao.is_not(None),
            )
            .group_by(PositionEvent.hex)
        ).all()
    }
    last_airport = {}
    if last_airport_ts:
        join_rows = session.execute(
            select(PositionEvent.hex, PositionEvent.nearest_airport_icao).where(
                tuple_(PositionEvent.hex, PositionEvent.snapshot_ts).in_(list(last_airport_ts.items()))
            )
        ).all()
        last_airport = {hex_code: airport for hex_code, airport in join_rows}

    existing_states = {
        state.hex: state
        for state in session.scalars(select(AircraftStateCurrent).where(AircraftStateCurrent.hex.in_(hexes))).all()
    }

    for event in snapshot_events:
        event_activity_24h = int(activity_24h.get(event.hex, 0))
        event_activity_72h = int(activity_72h.get(event.hex, 0))

        idle_minutes = None
        if event.altitude_is_ground and event.nearest_airport_icao and event.hex in prior_active:
            delta = event.snapshot_ts - prior_active[event.hex]
            idle_minutes = max(0, int(delta.total_seconds() // 60))

        score = _availability_score(event, idle_minutes, event_activity_24h)

        state = existing_states.get(event.hex)
        if state is None:
            state = AircraftStateCurrent(hex=event.hex, snapshot_ts=snapshot_ts, last_seen_at=snapshot_ts)
            session.add(state)
            existing_states[event.hex] = state

        state.snapshot_ts = event.snapshot_ts
        state.last_seen_at = _last_seen_at(event.snapshot_ts, event.seen_seconds)
        state.flight = event.flight
        state.reg = event.reg
        state.icaotype = event.icaotype
        state.aircraft_class = event.aircraft_class
        state.charter_relevant = event.charter_relevant
        state.relevance_reason = event.relevance_reason
        state.source_type = event.source_type
        state.lat = event.lat
        state.lon = event.lon
        state.altitude_baro = event.altitude_baro
        state.altitude_is_ground = event.altitude_is_ground
        state.ground_speed = event.ground_speed
        state.track = event.track
        state.nearest_airport_icao = event.nearest_airport_icao
        state.distance_to_airport_nm = event.distance_to_airport_nm
        state.idle_minutes = idle_minutes
        state.activity_24h = event_activity_24h
        state.activity_72h = event_activity_72h
        state.availability_score = score
        state.availability_band = _availability_band(score)
        state.last_airport_icao = event.nearest_airport_icao or last_airport.get(event.hex)
        state.updated_at = datetime.now(UTC)

    refresh_airport_supply(session, snapshot_ts)


def refresh_airport_supply(session: Session, snapshot_ts: datetime) -> None:
    session.execute(delete(AirportSupplySnapshot).where(AirportSupplySnapshot.snapshot_ts == snapshot_ts))

    grouped: dict[str, list[AircraftStateCurrent]] = defaultdict(list)
    current_states = list(
        session.scalars(select(AircraftStateCurrent).where(AircraftStateCurrent.snapshot_ts == snapshot_ts)).all()
    )
    for state in current_states:
        airport = state.last_airport_icao or state.nearest_airport_icao
        if airport:
            grouped[airport].append(state)

    for airport_icao, states in grouped.items():
        ranked_hexes = [state.hex for state in sorted(states, key=lambda item: item.availability_score, reverse=True)]
        snapshot = AirportSupplySnapshot(
            snapshot_ts=snapshot_ts,
            airport_icao=airport_icao,
            total_aircraft=len(states),
            charter_relevant_count=sum(1 for state in states if state.charter_relevant),
            top_aircraft_hexes=ranked_hexes[:10],
        )
        session.add(snapshot)
