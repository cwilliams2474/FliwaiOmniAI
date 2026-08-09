from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, agents, ai, assets, auth, billing, codex, documents, health, integrations, memory, monitoring, notifications, organizations, portal, security, tickets, workflows
from app.config import settings
from app.database.migrations import migrate_schema
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.logging_utils import configure_logging
from app.models import core  # noqa: F401
from app.scheduler import start_scheduler, stop_scheduler


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_schema()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, version='2.0.0', lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

for router in (health, auth, security, organizations, billing, portal, monitoring, admin, ai, codex, agents, memory, workflows, integrations, notifications, documents, tickets, assets):
    app.include_router(router.router)


@app.get('/')
def root():
    return {'name': 'FLIWAI OmniAI', 'status': 'online', 'version': '2.0.0'}
