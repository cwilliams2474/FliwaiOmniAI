import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.automation import scheduler
from app.routers import assets, auth, automation, chat, documents, health, integrations, memory, notifications, orgs, tickets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("omniai")


def create_app() -> FastAPI:
    s = get_settings()
    if s.is_production and (s.secret_key == "change-me" or len(s.secret_key) < 32):
        raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters in production.")
    s.upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if s.scheduler_enabled:
            scheduler.start()
        yield
        scheduler.stop()

    docs = None if s.is_production else "/api/docs"
    app = FastAPI(title=s.app_name, version=__version__, docs_url=docs, redoc_url=None, openapi_url="/api/openapi.json" if docs else None, lifespan=lifespan)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        if not request.url.path.startswith("/api/health/live"):
            log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Return one readable sentence plus the raw details for the UI.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "request"
        errors = [{"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": f"{field}: {first.get('msg', 'invalid value')}", "errors": errors})

    for r in (health.router, auth.router, orgs.router, tickets.router, assets.router, documents.router, memory.router, chat.router,
              notifications.router, integrations.router, automation.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
