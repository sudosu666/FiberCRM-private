from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
base_dir = Path(__file__).resolve().parents[1]
templates_dir = base_dir / "frontend" / "templates"
if not templates_dir.exists():
    templates_dir = Path(__file__).resolve().parents[2] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/dispatcher", response_class=HTMLResponse)
async def get_dispatcher_board(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dispatcher.html", {"request": request})


@router.get("/field", response_class=HTMLResponse)
async def get_field_mobile(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("field-ops.html", {"request": request})


@router.get("/workers", include_in_schema=False)
async def workers_alias() -> RedirectResponse:
    return RedirectResponse(url="/field", status_code=307)


@router.get("/warehouse", response_class=HTMLResponse)
async def get_warehouse_board(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("warehouse.html", {"request": request})


@router.get("/Dashboards", include_in_schema=False)
async def dashboards_root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/dispatcher", status_code=307)


@router.get("/Dashboards/", include_in_schema=False)
async def dashboards_root_slash_redirect() -> RedirectResponse:
    return RedirectResponse(url="/dispatcher", status_code=307)


@router.get("/Dashboards/fiber-crm-dashboard.html", include_in_schema=False)
async def dashboards_dispatcher_file_alias() -> RedirectResponse:
    return RedirectResponse(url="/dispatcher", status_code=307)


@router.get("/Dashboards/fiber-designer.html", include_in_schema=False)
async def dashboards_designer_file_alias() -> RedirectResponse:
    return RedirectResponse(url="/dispatcher", status_code=307)
