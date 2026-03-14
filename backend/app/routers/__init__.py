from .auth_router import router as auth_router
from .ui_router import router as ui_router

from .tasks_router import router as tasks_router
from .subscriber_requests_router import router as subscriber_requests_router
from .buildings_router import router as buildings_router
from .network_router import router as network_router
from .tenders_router import router as tenders_router
from .warehouse_router import router as warehouse_router
from .dispatch_router import router as dispatch_router

__all__ = [
    "auth_router",
    "ui_router",
    "tasks_router",
    "subscriber_requests_router",
    "buildings_router",
    "network_router",
    "tenders_router",
    "warehouse_router",
    "dispatch_router",
]
