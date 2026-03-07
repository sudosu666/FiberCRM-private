from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
base_dir = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(base_dir / "frontend" / "templates"))

@router.get("/dispatcher", response_class=HTMLResponse)
async def get_dispatcher_board(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@router.get("/field", response_class=HTMLResponse)
async def get_field_mobile(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("field-ops.html", {"request": request})
