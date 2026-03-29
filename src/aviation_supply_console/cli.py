from __future__ import annotations

import time
from datetime import UTC, datetime

import typer

from aviation_supply_console.core.config import get_settings
from aviation_supply_console.db.base import init_db, session_scope
from aviation_supply_console.services.ingestion import (
    backfill_window,
    import_live_snapshot,
    import_registry,
    import_snapshot,
)

app = typer.Typer(no_args_is_help=True)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@app.command("init-db")
def init_database() -> None:
    init_db()
    typer.echo("database initialized")


@app.command("import-registry")
def import_registry_command() -> None:
    with session_scope() as session:
        run = import_registry(session)
        typer.echo(f"registry import completed: {run.records_written} records")


@app.command("import-snapshot")
def import_snapshot_command(when: str = typer.Option(..., help="UTC timestamp, e.g. 2026-03-01T00:00:00Z")) -> None:
    snapshot_at = _parse_datetime(when)
    with session_scope() as session:
        run = import_snapshot(session, snapshot_at)
        typer.echo(f"snapshot import completed: {run.records_written} aircraft at {snapshot_at.isoformat()}")


@app.command("backfill-window")
def backfill_window_command(
    start: str = typer.Option(..., help="UTC timestamp, must be on the 1st of the month"),
    minutes: int = typer.Option(30, min=1),
    step_seconds: int = typer.Option(300, min=5),
) -> None:
    start_at = _parse_datetime(start)
    with session_scope() as session:
        runs = backfill_window(session, start_at, minutes=minutes, step_seconds=step_seconds)
        typer.echo(f"backfill completed: {len(runs)} snapshots imported")


@app.command("poll-live")
def poll_live_command(
    cycles: int = typer.Option(1, min=1, help="Number of poll cycles to run."),
    sleep_seconds: int | None = typer.Option(None, min=1, help="Override configured poll interval."),
) -> None:
    settings = get_settings()
    interval = sleep_seconds or settings.live_poll_interval_seconds
    for index in range(cycles):
        with session_scope() as session:
            run = import_live_snapshot(session)
            typer.echo(
                f"live poll {index + 1}/{cycles} completed: {run.records_written} aircraft via {settings.live_provider}"
            )
        if index < cycles - 1:
            time.sleep(interval)


if __name__ == "__main__":
    app()
