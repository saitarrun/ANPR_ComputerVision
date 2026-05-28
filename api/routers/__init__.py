"""API routers."""
from api.routers import auth, data, ingest, websocket, debug, watchlist, review, audit
from api.routers import settings as settings_router

__all__ = [
    "auth",
    "data",
    "ingest",
    "websocket",
    "debug",
    "watchlist",
    "review",
    "audit",
    "settings_router",
]
