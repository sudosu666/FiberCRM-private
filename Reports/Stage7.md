# Stage 7 Report — Warehouse

## Scope
- Реализовать складской поток стадии:
  - просмотр остатков материалов
  - просмотр заявок от проектировщика/исполнения
  - обработка заявки со списанием остатков
  - фиксация частичного и полного выполнения

## Completed
- Backend отдает warehouse API под роль `Warehouse`:
  - `GET /api/stock`
  - `GET /api/warehouse/requests`
  - `POST /api/warehouse/requests/{request_id}/fulfill`
- При обработке заявки backend:
  - списывает доступный остаток со `stock_items`
  - обновляет `fulfilled_qty` у `warehouse_request_items`
  - переводит заявку в `partial` или `fulfilled`
  - пишет запись в `stock_transactions`
- Warehouse UI (`/warehouse`) теперь работает через JWT и умеет:
  - показывать дефицит по позиции (`quantity < min_quantity`)
  - закрывать заявку кнопкой из интерфейса
  - честно показывать, что нужен логин комірника, если токена нет
- Автозаявка из designer/network plan остается частью общего execution-потока:
  - `POST /api/network/plan` создает `warehouse_request`
  - склад может обработать ее тем же Stage 7 endpoint

## Acceptance (Smoke)
- `/warehouse` -> `200`
- `GET /api/stock` для роли `Warehouse` -> `200`
- `GET /api/warehouse/requests` для роли `Warehouse` -> `200`
- `POST /api/warehouse/requests/{id}/fulfill` обновляет статус заявки и остатки
- `python -m compileall backend/app` без ошибок

## Notes
- Stage 7 приведен в соответствие с `stages.xlsx`; прежний отчет про dispatcher intelligence не соответствовал карте проекта.
- Текущее закрытие заявки использует режим “выполнить все доступное”; поштучная ручная аллокация по позициям может быть отдельным следующим улучшением.

## Next
- После перезагрузки окружения проверить live runtime на актуальном коде и уже затем решать, нужен ли отдельный модуль ручного распределения материалов по заявке.
