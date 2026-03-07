import socketio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import AsyncSessionLocal, init_db
from .routers import auth_router, logic_router, ui_router
from .seed import seed_demo_data
from .services.realtime import sio
from .models import UserRole

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(logic_router)
app.include_router(ui_router)

@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_demo_data(session)

@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "up", "backend": "fastapi"}

@app.get("/whoami")
async def who_am_i() -> dict[str, list[str]]:
    return {"stack": "Python + FastAPI", "roles": [role.value for role in UserRole]}

sio_app = socketio.ASGIApp(sio, app)
