"""Typed application settings loaded from environment / .env.

Every environment-specific value lives here so that no secret or tunable is
hard-coded elsewhere. See ``.env.example`` for the full list and
``docs/environment-setup.md`` for descriptions.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Environment ---
    # Set ENVIRONMENT=production in prod. Gates the dev-only OTP bypass and
    # demo-data seeding so neither can ship to a live deployment.
    environment: str = "development"

    # --- Database ---
    database_url: str = "sqlite:///./digimess.db"
    auto_migrate_on_startup: bool = True
    # Demo-data seeding is OFF by default. Enable explicitly for local dev only;
    # it must never populate a real deployment.
    auto_seed_on_startup: bool = False

    # --- Auth / JWT ---
    # No usable fallback: a real deployment must supply JWT_SECRET. Empty is only
    # tolerated outside production (see the validator below).
    jwt_secret: str = ""
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
    seed_admin_email: str = "admin@kadelivery.app"
    seed_pickup_delivery: bool = True
    seed_active_delivery: bool = False

    # --- Rider location policy ---
    location_update_interval_seconds: int = 5
    # A rider is only "genuinely online" if the app has checked in (posted a
    # location or gone online) within this window. Covers force-closed apps that
    # never send /rider/offline — they age out instead of showing online forever.
    online_heartbeat_timeout_seconds: int = 900  # 15 minutes
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
    # Optional operational override: if set, this rider is preferred by dispatch
    # when eligible. Empty (default) means "no preferred rider" — dispatch picks
    # the nearest eligible partner. No fabricated fallback address.
    default_rider_email: str = ""
    # Platform base fare paid to a rider per delivery (real pricing tunable, not
    # a model-level magic default).
    rider_base_fare_cents: int = 9000

    # --- WebSocket reconnect hints (surfaced to clients) ---
    ws_reconnect_base_ms: int = 1000
    ws_reconnect_max_ms: int = 15000

    # --- Stubbed integrations ---
    notification_provider: str = "dev"
    expo_access_token: str = ""
    payment_provider: str = "cod"
    # Shared secret the booking app sends (X-API-Key) to the ingestion endpoint.
    # Empty disables ingestion (endpoint returns 503) so it is never open by default.
    integration_api_key: str = ""

    # --- CORS ---
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @model_validator(mode="after")
    def _require_secrets_in_production(self) -> "Settings":
        """Fail fast: a production deployment must supply a real JWT secret."""
        if self.is_production and not self.jwt_secret.strip():
            raise ValueError(
                "JWT_SECRET must be set in production (no dev fallback is provided)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
