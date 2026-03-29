from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aviation_supply_console.api.routes import router
from aviation_supply_console.core.config import get_settings
from aviation_supply_console.db.base import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()

    app = FastAPI(title=settings.app_name)
    app.mount("/static", StaticFiles(directory="src/aviation_supply_console/static"), name="static")
    app.include_router(router)
    return app

