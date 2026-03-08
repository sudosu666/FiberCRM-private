# Stage 6 Report — Field Ops (PWA + Offline Sync)

## Scope
- Довести mobile flow до рабочей цепочки стадии:
  - задача -> шаги -> фото-звіт -> чат
  - офлайн-очередь и синхронизация при восстановлении сети.

## Completed
- Backend API для шагов задач:
  - `GET /api/tasks/{task_id}/steps`
  - `PATCH /api/tasks/{task_id}/steps/{step_id}/complete`
  - Файлы: `backend/app/routers/logic_router.py`, `backend/app/schemas.py`
- Mobile PWA (`/field`) обновлен:
  - шаги теперь загружаются из backend вместо только локального мока
  - завершение шага отправляется в backend endpoint `.../complete`
  - запросы к operational API выполняются с `Bearer` token, что согласует mobile flow с RBAC Stage 1/5
  - добавлена IndexedDB очередь офлайн-действий (`step`, `photo`, `chat`)
  - при `online` и при `socket connect` очередь автоматически синхронизируется
  - файл: `backend/frontend/static/mobile.js`
- PWA оболочка, manifest и service worker остаются рабочими:
  - `backend/frontend/templates/field-ops.html`
  - `backend/frontend/static/manifest.json`
  - `backend/frontend/static/sw.js`

## Acceptance (Smoke)
- `/field` -> `200`
- `GET /api/tasks/{id}/steps` -> `200`
- `PATCH /api/tasks/{id}/steps/{step_id}/complete` -> `200`
- `python -m compileall backend/app` без ошибок

## Notes
- Offline queue покрывает ключевые операции Stage 6 без изменения UX.
- Существующий лимит фото 200KB на client + backend 300KB (413) сохранён.
- Для реальной работы `/field` теперь требуется предварительный логин и наличие `fiberops_token` в браузере; без него UI остается в read-only/error состоянии.

## Next
- Stage 7 (Warehouse / materials flow by stages plan): дожать операции склада и интеграцию заявок в execution-процесс.
