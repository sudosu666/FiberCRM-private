from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from .database import engine, Base, AsyncSessionLocal
from .routers import auth_router, logic_router
from .seed import seed_demo_data
from .models import UserRole

app = FastAPI(title='FiberOps CRM Backend')

@app.on_event('startup')
async def on_startup():
    async with engine.begin() as conn:  # type: AsyncEngine
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await seed_demo_data(session)

app.include_router(auth_router)
app.include_router(logic_router)

@app.get('/')
async def health_check():
    return {'status': 'up', 'backend': 'fastapi'}

@app.get('/whoami')
async def who_am_i():
    return {'stack': 'Python + FastAPI', 'roles': [r.value for r in UserRole]}
