"""Effective-route inspection must support FastAPI's lazy included routers."""

from fastapi import APIRouter, FastAPI, WebSocket

from app.utils.route_inspection import iter_effective_routes


def test_nested_router_paths_and_methods_are_effective():
    inner = APIRouter()

    @inner.get("/ping")
    async def ping():
        return {"ok": True}

    @inner.websocket("/stream")
    async def stream(websocket: WebSocket):
        await websocket.close()

    outer = APIRouter(prefix="/v1")
    outer.include_router(inner, prefix="/nested")
    app = FastAPI()
    app.include_router(outer, prefix="/api")

    routes = list(iter_effective_routes(app.routes))
    paths = {getattr(route, "path", "") for route in routes}
    ping_route = next(
        route for route in routes if getattr(route, "path", "") == "/api/v1/nested/ping"
    )

    assert "/api/v1/nested/ping" in paths
    assert "/api/v1/nested/stream" in paths
    assert "GET" in (getattr(ping_route, "methods", None) or set())


def test_direct_routes_remain_visible():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    paths = {getattr(route, "path", "") for route in iter_effective_routes(app.routes)}

    assert "/health" in paths
