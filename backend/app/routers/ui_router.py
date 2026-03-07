from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
base_dir = Path(__file__).resolve().parents[1]
templates_dir = base_dir / "frontend" / "templates"
if not templates_dir.exists():
    templates_dir = Path(__file__).resolve().parents[1] / "frontend" / "templates"
    if not templates_dir.exists():
        templates_dir = Path(__file__).resolve().parents[2] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

@router.get("/dispatcher", response_class=HTMLResponse)
async def get_dispatcher_board(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@router.get("/field", response_class=HTMLResponse)
async def get_field_mobile(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("field-ops.html", {"request": request})
