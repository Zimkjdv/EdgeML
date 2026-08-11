from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.observability import RequestContextMiddleware, configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="EdgeML", version="0.7.3")
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(api_router, prefix="/api")
    app.include_router(health_router)

    return app


app = create_app()
