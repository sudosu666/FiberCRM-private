import socketio
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import settings
from .database import AsyncSessionLocal, engine, init_db
from .observability import init_sentry
from .routers import (
    auth_router,
    tasks_router,
    subscriber_requests_router,
    buildings_router,
    network_router,
    tenders_router,
    warehouse_router,
    dispatch_router,
    ui_router,
)
from .seed import seed_demo_data
from .services.realtime import sio
from .models import UserRole

init_sentry()
app = FastAPI(title=settings.app_name, docs_url="/api/docs", redoc_url=None)
allow_all_origins = settings.cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=not allow_all_origins,
)

app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(subscriber_requests_router)
app.include_router(buildings_router)
app.include_router(network_router)
app.include_router(tenders_router)
app.include_router(warehouse_router)
app.include_router(dispatch_router)
app.include_router(ui_router)

project_root = Path(__file__).resolve().parents[2]
static_dir = project_root / "frontend" / "app" / "static"
if not static_dir.exists():
    static_dir = Path(__file__).resolve().parents[1] / "frontend" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    if settings.seed_demo_data:
        async with AsyncSessionLocal() as session:
            await seed_demo_data(session)

@app.get("/")
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=307)

@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "live"}

@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready"}

@app.get("/whoami")
async def who_am_i() -> dict[str, list[str]]:
    return {"stack": "Python + FastAPI", "roles": [role.value for role in UserRole]}

sio_app = socketio.ASGIApp(sio, app)
