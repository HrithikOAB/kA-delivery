"""Typed application settings loaded from environment / .env.

Every environment-specific value lives here so that no secret or tunable is
hard-coded elsewhere. See ``.env.example`` for the full list and
``docs/environment-setup.md`` for descriptions.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database ---
    database_url: str = "sqlite:///./digimess.db"
    auto_migrate_on_startup: bool = True
    auto_seed_on_startup: bool = True

    # --- Auth / JWT ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # --- Base URLs (informational) ---
    api_base_url: str = "http://localhost:8000"
    ws_base_url: str = "ws://localhost:8000"

    # --- Maps ---
    map_provider: str = "none"
    google_maps_api_key: str = ""

    # --- Document uploads (partner verification) ---
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 MB per document

    # --- Admin seed (super admin created by app.seed) ---
    seed_admin_email: str = "admin@digimess.app"
    seed_pickup_delivery: bool = True
    seed_active_delivery: bool = False

    # --- Rider location policy ---
    location_update_interval_seconds: int = 5
    location_distance_threshold_meters: float = 30.0
    # Markers grey out after this many seconds without a fresh fix. Kept well
    # above the 5s post interval so brief network gaps don't drop live markers.
    location_stale_seconds: int = 90
    location_max_jump_meters: float = 2000.0
    location_max_speed_mps: float = 55.0

    # --- Tracking retention ---
    tracking_retention_hours: int = 24
    max_location_history: int = 500

    # --- OTP (delivery proof) ---
    otp_length: int = 4
    otp_expiry_minutes: int = 30
    default_otp: str = "1212"

    # --- Login OTP (customer phone sign-in) ---
    login_otp_length: int = 4
    login_otp_expiry_minutes: int = 5

    # --- Dispatch / batching ---
    dispatch_offer_timeout_seconds: int = 86400  # 24h; offers end only on accept/reject
    dispatch_max_batch_size: int = 1
    dispatch_max_mess_radius_km: float = 8.0
    default_rider_email: str = "rider@digimess.app"

    # --- WebSocket reconnect hints (surfaced to clients) ---
    ws_reconnect_base_ms: int = 1000
    ws_reconnect_max_ms: int = 15000

    # --- Stubbed integrations ---
    notification_provider: str = "dev"
    expo_access_token: str = ""
    payment_provider: str = "cod"

    # --- CORS ---
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
