"""FastAPI application entrypoint for the delivery partner API."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.ws_manager import manager
from app.api.v1 import (
    addresses,
    admin,
    auth,
    deliveries,
    maps,
    mess_ops,
    messes,
    orders,
    rider,
    tracking_ws,
)

# Import models so metadata is populated before create_all.
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.db_init import init_database

    init_database()
    manager.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="Khana Delivery Partner API",
    version="1.0.0",
    description="Delivery partner (rider) backend for Khana Anywhere.",
    lifespan=lifespan,
)

# `allow_origins=["*"]` with `allow_credentials=True` is an invalid combo that
# browsers reject. Only enable credentials when explicit origins are configured
# (set CORS_ORIGINS to your admin/web origins in production). Auth uses Bearer
# tokens, not cookies, so credentials can stay off for the wildcard dev case.
_cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


api = APIRouter(prefix="/api/v1")
api.include_router(auth.router)
api.include_router(rider.router)
api.include_router(maps.router)
api.include_router(deliveries.router)
api.include_router(messes.router)
api.include_router(addresses.router)
api.include_router(orders.router)
api.include_router(mess_ops.router)
api.include_router(admin.router)
api.include_router(tracking_ws.router)


@api.get("/config", tags=["config"])
def client_config() -> dict:
    """Non-secret tunables the mobile app needs."""
    return {
        "map_provider": settings.map_provider,
        "location_update_interval_seconds": settings.location_update_interval_seconds,
        "location_distance_threshold_meters": settings.location_distance_threshold_meters,
        "location_stale_seconds": settings.location_stale_seconds,
        "ws_reconnect_base_ms": settings.ws_reconnect_base_ms,
        "ws_reconnect_max_ms": settings.ws_reconnect_max_ms,
    }


app.include_router(api)


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "service": "Khana Delivery Partner API",
        "status": "ok",
        "docs": "/docs",
        "api": "/api/v1",
        "health": "/health",
    }


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
