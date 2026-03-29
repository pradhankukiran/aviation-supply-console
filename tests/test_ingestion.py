from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from aviation_supply_console.db.base import Base
from aviation_supply_console.models.entities import AircraftStateCurrent, PositionEvent
from aviation_supply_console.services import ingestion


def _sample_opensky_payload() -> dict:
    return {
        "time": 1774713771,
        "states": [
            [
                "ac4963",
                "DAL2401 ",
                "United States",
                1774713553,
                1774713553,
                -74.1872,
                40.6817,
                1000.0,
                False,
                100.0,
                180.0,
                0.0,
                None,
                1100.0,
                "3021",
                False,
                0,
                7,
            ]
        ],
    }


def test_normalize_opensky_payload_converts_units_and_fields() -> None:
    snapshot_ts, rows = ingestion._normalize_opensky_payload(_sample_opensky_payload())

    assert snapshot_ts == datetime.fromtimestamp(1774713771, UTC)
    assert len(rows) == 1

    row = rows[0]
    assert row["hex"] == "ac4963"
    assert row["flight"] == "DAL2401"
    assert row["category"] == "A6"
    assert row["type"] == "opensky_adsb"
    assert row["alt_baro"] == pytest.approx(3280.8, abs=0.1)
    assert row["gs"] == pytest.approx(194.4, abs=0.1)
    assert row["seen"] == pytest.approx(218.0, abs=0.1)
    assert row["seen_pos"] == pytest.approx(218.0, abs=0.1)


def test_import_live_snapshot_uses_opensky_provider(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    settings = SimpleNamespace(
        live_provider="opensky",
        live_snapshot_url=None,
        live_auth_header_name=None,
        live_auth_token=None,
        live_poll_interval_seconds=300,
        opensky_states_url="https://opensky-network.org/api/states/all",
        opensky_token_url="https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        opensky_client_id=None,
        opensky_client_secret=None,
        opensky_lamin=40.0,
        opensky_lomin=-75.0,
        opensky_lamax=41.0,
        opensky_lomax=-73.0,
        opensky_extended=True,
        raw_data_dir=tmp_path,
        airport_match_radius_nm=20.0,
    )

    captured: dict = {}

    def fake_fetch_json(url: str, *, headers=None, params=None) -> dict:
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return _sample_opensky_payload()

    monkeypatch.setattr(ingestion, "get_settings", lambda: settings)
    monkeypatch.setattr(ingestion, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(ingestion, "persist_raw", lambda path, payload: None)

    with SessionLocal() as session:
        run = ingestion.import_live_snapshot(session)
        session.flush()

        event = session.scalar(select(PositionEvent))
        current = session.get(AircraftStateCurrent, "ac4963")

    assert run.source == "opensky_live_states"
    assert run.status == "completed"
    assert run.records_seen == 1
    assert run.records_written == 1
    assert captured["url"] == "https://opensky-network.org/api/states/all"
    assert captured["headers"] is None
    assert captured["params"]["extended"] == 1
    assert captured["params"]["lamin"] == 40.0
    assert captured["params"]["lomin"] == -75.0
    assert event is not None
    assert event.hex == "ac4963"
    assert event.source_type == "opensky_adsb"
    assert event.flight == "DAL2401"
    assert event.altitude_baro == pytest.approx(3280.8, abs=0.1)
    assert current is not None
    assert current.hex == "ac4963"
