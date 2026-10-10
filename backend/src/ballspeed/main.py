import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from ballspeed.api import analysis, videos
from ballspeed.config import Settings, settings
from ballspeed.errors import ApiError, api_error_handler, validation_error_handler
from ballspeed.storage import Store


async def _sweeper(store: Store) -> None:
    while True:
        await asyncio.sleep(60)
        await asyncio.to_thread(store.sweep)


def create_app(cfg: Settings = settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(cfg.data_dir, ttl_s=cfg.ttl_minutes * 60)
        app.state.store = store
        task = asyncio.create_task(_sweeper(store))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            store.close()

    app = FastAPI(title="Ball speed estimator", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=cfg.cors_origins, allow_methods=["*"], allow_headers=["*"]
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(videos.router)
    app.include_router(analysis.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
