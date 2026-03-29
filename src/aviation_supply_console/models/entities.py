from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aviation_supply_console.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AircraftMaster(Base):
    __tablename__ = "aircraft_master"

    hex: Mapped[str] = mapped_column(String(7), primary_key=True)
    reg: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    icaotype: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_operator: Mapped[str | None] = mapped_column(String(256), nullable=True)
    faa_pia: Mapped[bool] = mapped_column(Boolean, default=False)
    faa_ladd: Mapped[bool] = mapped_column(Boolean, default=False)
    military: Mapped[bool] = mapped_column(Boolean, default=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PositionEvent(Base):
    __tablename__ = "aircraft_position_events"
    __table_args__ = (UniqueConstraint("snapshot_ts", "hex", name="uq_snapshot_hex"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hex: Mapped[str] = mapped_column(String(7), index=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    flight: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reg: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    icaotype: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(8), nullable=True)
    aircraft_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    charter_relevant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    relevance_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    altitude_baro: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_is_ground: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ground_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    track: Mapped[float | None] = mapped_column(Float, nullable=True)
    nearest_airport_icao: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    distance_to_airport_nm: Mapped[float | None] = mapped_column(Float, nullable=True)
    seen_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    seen_pos_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AircraftStateCurrent(Base):
    __tablename__ = "aircraft_state_current"

    hex: Mapped[str] = mapped_column(String(7), primary_key=True)
    snapshot_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    flight: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reg: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    icaotype: Mapped[str | None] = mapped_column(String(16), nullable=True)
    aircraft_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    charter_relevant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    relevance_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_baro: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_is_ground: Mapped[bool] = mapped_column(Boolean, default=False)
    ground_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    track: Mapped[float | None] = mapped_column(Float, nullable=True)
    nearest_airport_icao: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    distance_to_airport_nm: Mapped[float | None] = mapped_column(Float, nullable=True)
    idle_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activity_24h: Mapped[int] = mapped_column(Integer, default=0)
    activity_72h: Mapped[int] = mapped_column(Integer, default=0)
    availability_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    availability_band: Mapped[str] = mapped_column(String(16), default="low")
    last_airport_icao: Mapped[str | None] = mapped_column(String(8), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AirportSupplySnapshot(Base):
    __tablename__ = "airport_supply_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_ts", "airport_icao", name="uq_supply_snapshot_airport"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    airport_icao: Mapped[str] = mapped_column(String(8), index=True)
    total_aircraft: Mapped[int] = mapped_column(Integer, default=0)
    charter_relevant_count: Mapped[int] = mapped_column(Integer, default=0)
    top_aircraft_hexes: Mapped[list[str]] = mapped_column(JSON, default=list)

