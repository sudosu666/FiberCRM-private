# Stage 2 Report — Logic Core

## Scope
- Finish the Logic Core by wiring the tender/task state machine, GPON metrics, and every backend endpoint the dispatcher UI will query (task queue, brigade board, timeline, warehouse, stock, network topology/overview, and building metrics).
- Keep the services self-contained so later stages can extend the real-time/messaging layers without reworking RFCs or data contracts.

## Completed
- `services/logic.py` now exports GPON helpers, tender summaries, network overview, and a building-specific metric payload; all of these feed the `/api/tenders`, `/api/network/overview`, and `/api/buildings/{id}/network` endpoints alongside the existing task queue/brigade/stock topology routes.
- Task assignments flush/resync before commit so we can recalculate building infrastructure and tender statuses immediately (planning → in_progress → completed) and keep the UI in sync with the actual work being processed.
- The new endpoints reuse the SQLModel schema, aggregate building/task statistics, and emit network capacity numbers so the upcoming designer/dispatcher pages can draw charts, KPI cards, and GPON calculators without extra transformations.

## Next
- Stage 3 (DevOps Early) will containerize the stack, add CI/CD, and ship a TLS-enabled dev environment so we can run the backend + frontend together before moving on to Stage 4.
