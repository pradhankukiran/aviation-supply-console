from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AVIATION_", env_file=".env", extra="ignore")

    app_name: str = "Aviation Supply Console"
    database_url: str = "sqlite:///./data/aviation_supply.db"
    raw_data_dir: Path = Path("./data/raw")
    registry_url: str = "https://downloads.adsbexchange.com/downloads/basic-ac-db.json.gz"
    historical_base_url: str = "https://samples.adsbexchange.com/readsb-hist"
    live_provider: str = "opensky"
    live_snapshot_url: str | None = None
    live_auth_header_name: str | None = None
    live_auth_token: str | None = None
    live_poll_interval_seconds: int = 300
    opensky_states_url: str = "https://opensky-network.org/api/states/all"
    opensky_token_url: str = (
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
    )
    opensky_client_id: str | None = None
    opensky_client_secret: str | None = None
    opensky_lamin: float | None = 24.0
    opensky_lomin: float | None = -126.0
    opensky_lamax: float | None = 50.0
    opensky_lomax: float | None = -66.0
    opensky_extended: bool = True
    default_airport_country: str = "US"
    airport_match_radius_nm: float = 20.0
    route_search_radius_nm: float = 250.0
    api_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.raw_data_dir.mkdir(parents=True, exist_ok=True)
    return settings
