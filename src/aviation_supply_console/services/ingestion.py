from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from aviation_supply_console.core.config import get_settings
from aviation_supply_console.models.entities import AircraftMaster, IngestionRun, PositionEvent
from aviation_supply_console.services.airports import nearest_airport
from aviation_supply_console.services.classification import classify_aircraft
from aviation_supply_console.services.http import fetch_bytes, fetch_json, maybe_decompress, persist_raw, post_form_json
from aviation_supply_console.services.state_engine import refresh_current_state


METERS_TO_FEET = 3.28084
METERS_PER_SECOND_TO_KNOTS = 1.94384
TOKEN_REFRESH_MARGIN_SECONDS = 30
OPENSKY_POSITION_SOURCES = {
    0: "opensky_adsb",
    1: "opensky_asterix",
    2: "opensky_mlat",
    3: "opensky_flarm",
}
OPENSKY_CATEGORY_MAP = {
    2: "A1",
    3: "A2",
    4: "A3",
    5: "A4",
    6: "A5",
    7: "A6",
    8: "A7",
}
_opensky_token: str | None = None
_opensky_token_expires_at: datetime | None = None


def _normalize_hex(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def _snapshot_path(snapshot_at: datetime) -> str:
    if snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=UTC)
    snapshot_at = snapshot_at.astimezone(UTC)
    if snapshot_at.day != 1:
        raise ValueError("ADS-B Exchange sample archives expose the 1st day of each month only.")
    return f"{snapshot_at:%Y/%m/01/%H%M%SZ}.json.gz"


def _snapshot_url(snapshot_at: datetime) -> str:
    settings = get_settings()
    return f"{settings.historical_base_url}/{_snapshot_path(snapshot_at)}"


def _raw_snapshot_target(snapshot_at: datetime) -> Path:
    settings = get_settings()
    return settings.raw_data_dir / "readsb-hist" / _snapshot_path(snapshot_at).replace(".json.gz", ".json")


def _raw_registry_target() -> Path:
    settings = get_settings()
    return settings.raw_data_dir / "registry" / "basic-ac-db.jsonl"


def _raw_live_target(provider: str, requested_at: datetime) -> Path:
    settings = get_settings()
    return settings.raw_data_dir / "live" / provider / f"{requested_at:%Y/%m/%d/%H%M%SZ}.json"


def _coerce_altitude(raw_altitude: Any) -> tuple[float | None, bool]:
    if raw_altitude == "ground":
        return 0.0, True
    if raw_altitude is None:
        return None, False
    return float(raw_altitude), False


def _meters_to_feet(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * METERS_TO_FEET, 1)


def _meters_per_second_to_knots(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * METERS_PER_SECOND_TO_KNOTS, 1)


def _normalize_opensky_category(raw_category: Any) -> str | None:
    if raw_category is None:
        return None
    try:
        return OPENSKY_CATEGORY_MAP.get(int(raw_category))
    except (TypeError, ValueError):
        return None


def _batched(rows: Iterable[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _upsert_aircraft_master(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    dialect_name = session.bind.dialect.name if session.bind else ""
    insert_builder = sqlite_insert if dialect_name == "sqlite" else postgres_insert
    stmt = insert_builder(AircraftMaster).values(rows)
    update_columns = {
        "reg": stmt.excluded.reg,
        "icaotype": stmt.excluded.icaotype,
        "manufacturer": stmt.excluded.manufacturer,
        "model": stmt.excluded.model,
        "owner_operator": stmt.excluded.owner_operator,
        "faa_pia": stmt.excluded.faa_pia,
        "faa_ladd": stmt.excluded.faa_ladd,
        "military": stmt.excluded.military,
        "source_updated_at": stmt.excluded.source_updated_at,
    }
    session.execute(stmt.on_conflict_do_update(index_elements=[AircraftMaster.hex], set_=update_columns))


def _legacy_live_headers() -> dict[str, str] | None:
    settings = get_settings()
    if settings.live_auth_header_name and settings.live_auth_token:
        return {settings.live_auth_header_name: settings.live_auth_token}
    return None


def _opensky_query_params() -> dict[str, Any]:
    settings = get_settings()
    params: dict[str, Any] = {}
    if None not in (
        settings.opensky_lamin,
        settings.opensky_lomin,
        settings.opensky_lamax,
        settings.opensky_lomax,
    ):
        params.update(
            {
                "lamin": settings.opensky_lamin,
                "lomin": settings.opensky_lomin,
                "lamax": settings.opensky_lamax,
                "lomax": settings.opensky_lomax,
            }
        )
    if settings.opensky_extended:
        params["extended"] = 1
    return params


def _opensky_scope_details() -> dict[str, Any]:
    params = _opensky_query_params()
    scope_keys = ("lamin", "lomin", "lamax", "lomax")
    if all(key in params for key in scope_keys):
        return {"bbox": {key: params[key] for key in scope_keys}, "extended": bool(params.get("extended"))}
    return {"bbox": None, "extended": bool(params.get("extended"))}


def _opensky_access_token() -> str | None:
    global _opensky_token, _opensky_token_expires_at

    settings = get_settings()
    if not settings.opensky_client_id or not settings.opensky_client_secret:
        return None

    now = datetime.now(UTC)
    if _opensky_token and _opensky_token_expires_at and now < _opensky_token_expires_at:
        return _opensky_token

    payload = post_form_json(
        settings.opensky_token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": settings.opensky_client_id,
            "client_secret": settings.opensky_client_secret,
        },
    )
    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 1800))
    _opensky_token = token
    _opensky_token_expires_at = now + timedelta(seconds=max(0, expires_in - TOKEN_REFRESH_MARGIN_SECONDS))
    return _opensky_token


def _opensky_headers() -> dict[str, str] | None:
    token = _opensky_access_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def _normalize_adsbexchange_payload(payload: dict[str, Any]) -> tuple[datetime, list[dict[str, Any]]]:
    snapshot_ts = datetime.fromtimestamp(float(payload["now"]), UTC)
    aircraft_rows: list[dict[str, Any]] = payload.get("aircraft", [])
    return snapshot_ts, aircraft_rows


def _normalize_opensky_payload(payload: dict[str, Any]) -> tuple[datetime, list[dict[str, Any]]]:
    snapshot_ts = datetime.fromtimestamp(float(payload["time"]), UTC)
    aircraft_rows: list[dict[str, Any]] = []
    for state in payload.get("states") or []:
        if not state or len(state) < 17:
            continue

        time_position = state[3]
        last_contact = state[4]
        altitude = state[7] if state[7] is not None else state[13]
        seen_seconds = max(0.0, float(snapshot_ts.timestamp() - last_contact)) if last_contact is not None else None
        seen_pos_seconds = (
            max(0.0, float(snapshot_ts.timestamp() - time_position))
            if time_position is not None
            else None
        )

        aircraft_rows.append(
            {
                "hex": state[0],
                "flight": (state[1] or "").strip() or None,
                "category": _normalize_opensky_category(state[17] if len(state) > 17 else None),
                "lat": state[6],
                "lon": state[5],
                "alt_baro": "ground" if bool(state[8]) else _meters_to_feet(altitude),
                "gs": _meters_per_second_to_knots(state[9]),
                "track": state[10],
                "seen": seen_seconds,
                "seen_pos": seen_pos_seconds,
                "type": OPENSKY_POSITION_SOURCES.get(state[16], "opensky_unknown"),
                "origin_country": state[2],
                "raw_state": state,
            }
        )

    return snapshot_ts, aircraft_rows


def _process_aircraft_rows(
    session: Session,
    *,
    run: IngestionRun,
    snapshot_ts: datetime,
    aircraft_rows: list[dict[str, Any]],
) -> IngestionRun:
    run.records_seen = len(aircraft_rows)

    session.execute(delete(PositionEvent).where(PositionEvent.snapshot_ts == snapshot_ts))
    existing_master = {
        master.hex: master
        for master in session.scalars(
            select(AircraftMaster).where(
                AircraftMaster.hex.in_(
                    [hex_code for hex_code in (_normalize_hex(row.get("hex")) for row in aircraft_rows) if hex_code]
                )
            )
        ).all()
    }

    inserted = 0
    for row in aircraft_rows:
        hex_code = _normalize_hex(row.get("hex"))
        if not hex_code:
            continue

        master = existing_master.get(hex_code)
        if master is None:
            master = AircraftMaster(hex=hex_code, source_updated_at=datetime.now(UTC))
            session.add(master)
            existing_master[hex_code] = master

        reg = row.get("r") or row.get("reg") or master.reg
        icaotype = row.get("t") or row.get("icaotype") or master.icaotype
        master.reg = reg or master.reg
        master.icaotype = icaotype or master.icaotype

        classification = classify_aircraft(
            type_code=icaotype,
            reg=reg,
            category=row.get("category"),
            military=bool(master.military),
        )

        altitude_baro, altitude_is_ground = _coerce_altitude(row.get("alt_baro"))
        airport = nearest_airport(row.get("lat"), row.get("lon"))

        event = PositionEvent(
            snapshot_ts=snapshot_ts,
            hex=hex_code,
            source_type=row.get("type") or row.get("source_type"),
            flight=((row.get("flight") or row.get("callsign")) or "").strip() or None,
            reg=reg,
            icaotype=icaotype,
            category=row.get("category"),
            aircraft_class=classification.aircraft_class,
            charter_relevant=classification.charter_relevant,
            relevance_reason=classification.reason,
            lat=row.get("lat"),
            lon=row.get("lon"),
            altitude_baro=altitude_baro,
            altitude_is_ground=altitude_is_ground,
            ground_speed=row.get("gs"),
            track=row.get("track"),
            nearest_airport_icao=airport.icao if airport else None,
            distance_to_airport_nm=airport.distance_nm if airport else None,
            seen_seconds=row.get("seen") or row.get("seen_seconds"),
            seen_pos_seconds=row.get("seen_pos") or row.get("seen_pos_seconds"),
            raw=row,
        )
        session.add(event)
        inserted += 1

    run.status = "completed"
    run.records_written = inserted
    run.completed_at = datetime.now(UTC)
    refresh_current_state(session, snapshot_ts)
    return run


def import_registry(session: Session) -> IngestionRun:
    settings = get_settings()
    run = IngestionRun(source="adsbexchange_registry", details={"url": settings.registry_url})
    session.add(run)
    session.flush()

    try:
        raw_bytes = fetch_bytes(settings.registry_url)
        text = maybe_decompress(raw_bytes).decode("utf-8")
        persist_raw(_raw_registry_target(), text.encode("utf-8"))

        rows = []
        records_seen = 0
        imported = 0
        imported_at = datetime.now(UTC)
        for line in text.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            hex_code = _normalize_hex(payload.get("icao"))
            if not hex_code:
                continue

            rows.append(
                {
                    "hex": hex_code,
                    "reg": payload.get("reg"),
                    "icaotype": payload.get("icaotype"),
                    "manufacturer": payload.get("manufacturer"),
                    "model": payload.get("model"),
                    "owner_operator": payload.get("ownop"),
                    "faa_pia": bool(payload.get("faa_pia")),
                    "faa_ladd": bool(payload.get("faa_ladd")),
                    "military": bool(payload.get("mil")),
                    "source_updated_at": imported_at,
                }
            )
            records_seen += 1

        for batch in _batched(rows, size=5000):
            _upsert_aircraft_master(session, batch)
            session.flush()
            imported += len(batch)

        run.status = "completed"
        run.records_seen = records_seen
        run.records_written = imported
        run.completed_at = datetime.now(UTC)
        return run
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(UTC)
        raise


def import_snapshot(session: Session, snapshot_at: datetime) -> IngestionRun:
    url = _snapshot_url(snapshot_at)
    run = IngestionRun(source="adsbexchange_snapshot", details={"url": url, "requested_at": snapshot_at.isoformat()})
    session.add(run)
    session.flush()

    try:
        raw_bytes = fetch_bytes(url)
        payload = json.loads(maybe_decompress(raw_bytes).decode("utf-8"))
        persist_raw(_raw_snapshot_target(snapshot_at), maybe_decompress(raw_bytes))
        snapshot_ts, aircraft_rows = _normalize_adsbexchange_payload(payload)
        return _process_aircraft_rows(session, run=run, snapshot_ts=snapshot_ts, aircraft_rows=aircraft_rows)
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(UTC)
        raise


def import_live_snapshot(session: Session) -> IngestionRun:
    settings = get_settings()
    requested_at = datetime.now(UTC)
    provider = settings.live_provider.strip().lower()

    if provider == "opensky":
        auth_mode = "oauth2_client_credentials" if settings.opensky_client_id and settings.opensky_client_secret else "anonymous"
        details = {
            "provider": "opensky",
            "url": settings.opensky_states_url,
            "requested_at": requested_at.isoformat(),
            "auth_mode": auth_mode,
            **_opensky_scope_details(),
        }
        run = IngestionRun(source="opensky_live_states", details=details)
        session.add(run)
        session.flush()

        try:
            payload = fetch_json(
                settings.opensky_states_url,
                headers=_opensky_headers(),
                params=_opensky_query_params(),
            )
            persist_raw(_raw_live_target("opensky", requested_at), json.dumps(payload).encode("utf-8"))
            snapshot_ts, aircraft_rows = _normalize_opensky_payload(payload)
            return _process_aircraft_rows(session, run=run, snapshot_ts=snapshot_ts, aircraft_rows=aircraft_rows)
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            raise

    if provider in {"custom", "adsbexchange"}:
        if not settings.live_snapshot_url:
            raise ValueError("Set AVIATION_LIVE_SNAPSHOT_URL to use the custom live collector.")

        run = IngestionRun(
            source="adsbexchange_live_snapshot",
            details={
                "provider": provider,
                "url": settings.live_snapshot_url,
                "requested_at": requested_at.isoformat(),
            },
        )
        session.add(run)
        session.flush()

        try:
            raw_bytes = fetch_bytes(settings.live_snapshot_url, headers=_legacy_live_headers())
            payload = json.loads(maybe_decompress(raw_bytes).decode("utf-8"))
            persist_raw(_raw_live_target(provider, requested_at), maybe_decompress(raw_bytes))
            snapshot_ts, aircraft_rows = _normalize_adsbexchange_payload(payload)
            return _process_aircraft_rows(session, run=run, snapshot_ts=snapshot_ts, aircraft_rows=aircraft_rows)
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            raise

    raise ValueError(f"Unsupported AVIATION_LIVE_PROVIDER: {settings.live_provider}")


def backfill_window(session: Session, start: datetime, minutes: int, step_seconds: int) -> list[IngestionRun]:
    runs: list[IngestionRun] = []
    total_steps = max(1, int((minutes * 60) / step_seconds))
    current = start
    for _ in range(total_steps):
        runs.append(import_snapshot(session, current))
        session.flush()
        current += timedelta(seconds=step_seconds)
    return runs
