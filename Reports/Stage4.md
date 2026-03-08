# Stage 4 Report — Designer UI (Aligned to Dashboards Prototype)

## Scope
- Реализовать дизайнерский модуль в том же UX-виде, что и `/Dashboards/fiber-designer.html`, без нового дизайна.
- Подключить существующий экран к backend API и сохранить план так, чтобы он сразу попадал рабочим через задачи.

## Completed
- `/designer` теперь отдает dashboard-версию проектувальника (через `Dashboards/fiber-designer.html`), а не отдельный новый макет:
  - `backend/app/routers/ui_router.py`
- В `Dashboards/fiber-designer.html` добавлена backend-интеграция:
  - загрузка `GET /api/network/topology`, `GET /api/stock`, `GET /api/tenders`
  - `savePlan()` теперь вызывает `POST /api/network/plan`
  - после сохранения возвращается `building_id`, `task_ids`, `warehouse_request_id`
- Для контейнерного fallback тот же файл продублирован в:
  - `backend/frontend/templates/designer.html`
  чтобы вид и логика не зависели от наличия папки `Dashboards` внутри контейнера.

## Acceptance (Smoke)
- `GET /designer` -> `200`
- В отданной странице присутствуют backend-hook'и `API_BASE='/api'` и `/network/plan` (проверено через TestClient).
- `POST /api/network/plan` -> `201` (создание building + задач + warehouse request).

## Outcome for field teams
- Проектувальник сохраняет план в привычном интерфейсе `/Dashboards`.
- После `save plan` задачи автоматически создаются в backend и становятся доступными рабочим через их поток задач.

## Next
- Перейти к следующей стадии из `stages.xlsx` (Stage 5: Real-time Ops) и проверить соответствие текущей реализации критериям stage.
