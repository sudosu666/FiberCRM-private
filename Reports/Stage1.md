# Stage 1 Report — Foundation

## Scope
- Align the backend stack with Python 3.12 + FastAPI + SQLModel + PostgreSQL, mirroring the `Plan/fiberops_schema.sql` definition.
- Replace the legacy SQLAlchemy models/session with async SQLModel tables and expose the canonical dispatcher UI route.
- Establish Socket.IO scaffolding, role-aware rooms, and broadcast helpers so the Stage 5 real-time layer has a solid foundation.

## Completed
- `app/models.py` now declares every table/enum from the plan using UUID primary keys, SQLModel relationships, and the requested defaults/constraints.
- `app/database.py` exposes `init_db` + `get_session` on an async engine backed by SQLModel metadata, and `main.py` wires startup initialization + seeds.
- Auth flow now validates via `phone`, issues JWTs with `TokenData`, and documents the new `UserCreate`/`UserRead` payloads; the requirements list adds `sqlmodel` and `python-socketio[asyncio]`.
- Key Stage 1 gap found during Stage 5 audit and now closed: role checks are enforced on the main operational API paths, so dispatcher/designer/warehouse/field flows no longer share the same unrestricted backend surface.
- `app/services/realtime.py` hosts the Socket.IO server, dispatcher/brigade rooms, and a broadcast manager consumed by `logic_router`; `main.py` now surfaces `sio_app`.
- A dedicated HTMX `ui_router` renders `backend/frontend/templates/dispatcher.html` to prove the UI integration and gives a launcher for future Stage 5 work.
- README and stage report now describe the new stack, commands, and traceability back to the fiberops schema.

## Next
- Stage 2 (Logic Core) will continue wiring the task/tender state machine, GPON calculations, and the brigade/warehouse endpoints referenced by the frontend.
