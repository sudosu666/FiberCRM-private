# FiberOps API Routes Inventory

Краткий каталог рабочих роутов backend. Для каждого роута указано назначение, вход, обязательные поля, куда пишет данные и что возвращает.

## Auth

### `POST /token`
- Назначение: OAuth2 login form flow.
- Принимает: form-data.
- Обязательные поля:
  - `username`
  - `password`
- Пишет в: ничего, только выдаёт JWT.
- Возвращает: `Token`.
- Доступ: публичный.

### `POST /auth/login`
- Назначение: JSON login для UI.
- Принимает: JSON.
- Обязательные поля:
  - `phone`
  - `password`
- Пишет в: ничего, только выдаёт JWT.
- Возвращает: `Token`.
- Доступ: публичный.

### `GET /auth/me`
- Назначение: получить текущего пользователя.
- Принимает: `Authorization: Bearer`.
- Пишет в: ничего.
- Возвращает: `UserRead`.
- Доступ: любой авторизованный пользователь.

### `GET /auth/users`
- Назначение: список пользователей и ролей.
- Принимает: только JWT.
- Пишет в: ничего.
- Возвращает: `list[UserRead]`.
- Доступ: `Dispatcher`.

### `PATCH /auth/users/{user_id}/roles`
- Назначение: обновить primary role, additional roles, active flag.
- Принимает: JSON.
- Обязательные поля:
  - `role`
- Необязательные поля:
  - `additional_roles`
  - `is_active`
- Пишет в: `users`.
- Возвращает: `UserRead`.
- Доступ: `Dispatcher`.

### `POST /users`
- Назначение: создать пользователя.
- Принимает: JSON.
- Обязательные поля:
  - `name`
  - `phone`
  - `password`
  - `role`
- Необязательные поля:
  - `email`
  - `additional_roles`
- Пишет в: `users`.
- Возвращает: `UserRead`.
- Доступ: публичный, но rate-limited.

## Build Ops

### `GET /api/tasks`
- Назначение: очередь задач.
- Принимает: только JWT.
- Пишет в: ничего.
- Возвращает: `list[TaskQueueItem]`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.
- Примечание: полевые роли видят только свои бригады.

### `GET /api/tasks/{task_id}/steps`
- Назначение: шаги конкретной задачи.
- Принимает: path `task_id`.
- Пишет в: ничего.
- Возвращает: `list[TaskStepRead]`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `PATCH /api/tasks/{task_id}/steps/{step_id}/complete`
- Назначение: отметить шаг выполненным.
- Принимает: path `task_id`, `step_id`.
- Пишет в: `task_steps`, `tasks`, `work_logs`.
- Возвращает: `TaskStepCompleteRead`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `PATCH /api/tasks/{task_id}/start`
- Назначение: старт задачи.
- Принимает: path `task_id`.
- Пишет в: `tasks`, `work_logs`.
- Возвращает: `TaskStatusEventRead`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `PATCH /api/tasks/{task_id}/finish`
- Назначение: завершение задачи.
- Принимает: path `task_id`.
- Пишет в: `tasks`, `work_logs`.
- Возвращает: `TaskStatusEventRead`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `PATCH /api/tasks/{task_id}/hold`
- Назначение: призупинити задачу.
- Принимает: JSON.
- Обязательные поля:
  - `reason`
- Необязательные поля:
  - `is_critical`
- Пишет в: `tasks`, `work_logs`.
- Возвращает: `TaskStatusEventRead`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `PATCH /api/tasks/{task_id}/postpone`
- Назначение: перенести задачу на другую смену.
- Принимает: JSON.
- Обязательные поля:
  - `reason`
- Пишет в: `tasks`, `work_logs`, `ops_comments` c `comment_type=postpone`.
- Возвращает: `TaskStatusEventRead`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `POST /api/tasks/{task_id}/assign`
- Назначение: назначить задачу на бригаду.
- Принимает: JSON.
- Обязательные поля:
  - `brigade_id`
- Пишет в: `tasks`, `work_logs`.
- Возвращает: `TaskQueueItem`.
- Доступ: `Dispatcher`.

### `GET /api/tasks/{task_id}/work-summary`
- Назначение: журнал работ по задаче.
- Принимает: path `task_id`.
- Пишет в: ничего.
- Возвращает: `WorkSummaryRead`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `GET /api/tasks/{task_id}/comments`
- Назначение: служебные комментарии по задаче.
- Принимает: path `task_id`.
- Пишет в: ничего.
- Возвращает: `list[OpsCommentRead]`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `POST /api/tasks/{task_id}/comments`
- Назначение: добавить комментарий по задаче.
- Принимает: JSON.
- Обязательные поля:
  - `body`
  - `comment_type`
- Необязательные поля:
  - `role_tags`
- Пишет в: `ops_comments`.
- Возвращает: `OpsCommentRead`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `GET /api/tasks/{task_id}/contacts`
- Назначение: допконтакты по задаче.
- Принимает: path `task_id`.
- Пишет в: ничего.
- Возвращает: `list[OpsContactRead]`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `POST /api/tasks/{task_id}/contacts`
- Назначение: добавить допконтакт к задаче.
- Принимает: JSON.
- Обязательные поля:
  - `title`
  - `phone`
- Необязательные поля:
  - `full_name`
  - `notes`
- Пишет в: `ops_contacts`.
- Возвращает: `OpsContactRead`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `POST /api/tasks/{task_id}/reports`
- Назначение: фотоотчёт по задаче.
- Принимает: JSON.
- Обязательные поля:
  - `photo_filename`
  - `photo_data`
- Необязательные поля:
  - `comment`
  - `brigade_id`
  - `brigade_name`
- Пишет в: `task_reports`, `work_logs`, files under `/static/uploads`.
- Возвращает: `TaskReportRead`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `GET /api/brigades`
- Назначение: доска бригад.
- Возвращает: `list[BrigadeBoardItem]`.
- Доступ: `Dispatcher`.

### `POST /api/brigades`
- Назначение: создать бригаду.
- Принимает: JSON.
- Обязательные поля:
  - `name`
  - `type`
- Необязательные поля:
  - `foreman_id`
  - `member_ids`
  - `is_active`
- Пишет в: `brigades`, `brigade_members`.
- Возвращает: `BrigadeBoardItem`.
- Доступ: `Dispatcher`.

### `PATCH /api/brigades/{brigade_id}`
- Назначение: обновить бригаду.
- Принимает: JSON.
- Обязательные поля:
  - `name`
  - `type`
- Необязательные поля:
  - `foreman_id`
  - `member_ids`
  - `is_active`
- Пишет в: `brigades`, `brigade_members`.
- Возвращает: `BrigadeBoardItem`.
- Доступ: `Dispatcher`.

### `GET /api/field/workers`
- Назначение: список полевых работников.
- Возвращает: `list[FieldWorkerRead]`.
- Доступ: `Dispatcher`, `ConnectionDispatcher`.

### `GET /api/field/metrics`
- Назначение: общие field KPI.
- Возвращает: `FieldMetrics`.
- Доступ: `Builder`, `Welder`, `Connector`.

### `GET /api/timeline`
- Назначение: диспетчерский таймлайн.
- Возвращает: `list[TimelineHour]`.
- Доступ: `Dispatcher`.

### `GET /api/dispatch/stats`
- Назначение: агрегированная статистика задач.
- Query:
  - `status`
  - `task_type`
  - `brigade_id`
  - `city`
  - `critical_only`
  - `search`
- Пишет в: ничего.
- Возвращает: `DispatchStatsRead`.
- Доступ: `Dispatcher`.

### `GET /api/dispatch/workers/stats`
- Назначение: статистика по работникам.
- Query:
  - `role`
  - `brigade_id`
  - `search`
- Возвращает: `list[WorkerStatsRead]`.
- Доступ: `Dispatcher`.

## Subscriber Requests / Connection Dispatch

### `GET /api/subscriber-requests`
- Назначение: очередь одиночных заявок на подключение.
- Возвращает: `list[SubscriberRequestRead]`.
- Доступ: `Dispatcher`, `ConnectionDispatcher`.

### `GET /api/subscriber-requests/summary`
- Назначение: summary по заявкам на подключение.
- Возвращает: `SubscriberDispatcherSummary`.
- Доступ: `Dispatcher`, `ConnectionDispatcher`.

### `POST /api/subscriber-requests`
- Назначение: создать одиночную заявку на подключение.
- Принимает: JSON.
- Обязательные поля:
  - `building_id`
  - `flat_number`
  - `customer_name`
  - `phone`
- Необязательные поля:
  - `notes`
- Пишет в: `subscriber_requests`.
- Возвращает: `SubscriberRequestRead`.
- Доступ: `Dispatcher`, `ConnectionDispatcher`.

### `PATCH /api/subscriber-requests/{request_id}/schedule`
- Назначение: назначить дату и слот выезда.
- Принимает: JSON.
- Обязательные поля:
  - `scheduled_date`
  - `arrival_window`
  - `assigned_user_id`
- Пишет в: `subscriber_requests`.
- Возвращает: `SubscriberRequestRead`.
- Доступ: `ConnectionDispatcher`.

### `PATCH /api/subscriber-requests/{request_id}/postpone`
- Назначение: перенести заявку.
- Принимает: JSON.
- Обязательные поля:
  - `reason`
- Пишет в: `subscriber_requests`, `ops_comments` c `comment_type=postpone`.
- Возвращает: `SubscriberRequestRead`.
- Доступ: `ConnectionDispatcher`.

### `GET /api/subscriber-requests/{request_id}/comments`
### `POST /api/subscriber-requests/{request_id}/comments`
- Назначение: читать/писать комментарии заявки.
- Для `POST` обязательные поля:
  - `body`
  - `comment_type`
- Необязательные поля:
  - `role_tags`
- Пишет в: `ops_comments`.
- Возвращает: `list[OpsCommentRead]` или `OpsCommentRead`.
- Доступ: `Dispatcher`, `ConnectionDispatcher`.

### `GET /api/subscriber-requests/{request_id}/contacts`
### `POST /api/subscriber-requests/{request_id}/contacts`
- Назначение: читать/писать допконтакты заявки.
- Для `POST` обязательные поля:
  - `title`
  - `phone`
- Необязательные поля:
  - `full_name`
  - `notes`
- Пишет в: `ops_contacts`.
- Возвращает: `list[OpsContactRead]` или `OpsContactRead`.
- Доступ: `Dispatcher`, `ConnectionDispatcher`.

## Buildings / Registry

### `GET /api/buildings`
- Назначение: summary по домам.
- Возвращает: `list[BuildingSummaryRead]`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `GET /api/buildings/{building_id}/network`
- Назначение: сетевые метрики дома.
- Возвращает: `BuildingNetworkRead`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `GET /api/buildings/{building_id}/notes`
### `POST /api/buildings/{building_id}/notes`
- Назначение: legacy notes по дому.
- Для `POST` обязательные поля:
  - `body`
- Необязательные поля:
  - `role_tags`
- Пишет в: `building_notes`.
- Возвращает: `list[BuildingNoteRead]` или `BuildingNoteRead`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `GET /api/buildings/{building_id}/comments`
### `POST /api/buildings/{building_id}/comments`
- Назначение: единый журнал комментариев по дому.
- Для `POST` обязательные поля:
  - `body`
  - `comment_type`
- Необязательные поля:
  - `role_tags`
- Пишет в: `ops_comments`.
- Возвращает: `list[OpsCommentRead]` или `OpsCommentRead`.
- Доступ: `Dispatcher`, `Builder`, `Welder`, `Connector`.

### `GET /api/network/infrastructure`
- Назначение: реестр введённой инфраструктуры.
- Возвращает: `list[InfrastructureBuildingRead]`.
- Доступ: `Dispatcher`.

## Designer / Network Planning

### `GET /api/network/topology`
- Назначение: список муфт и волокон.
- Возвращает: `list[NetworkMuffleRead]`.
- Доступ: `Designer`.

### `GET /api/network/overview`
- Назначение: summary по сети.
- Возвращает: `NetworkOverview`.
- Доступ: `Designer`.

### `POST /api/network/buildings/{building_id}/calculate`
- Назначение: расчёт дома.
- Пишет в: ничего.
- Возвращает: `BuildingCalculateRead`.
- Доступ: `Designer`.

### `GET /api/network/muffles/{muffle_id}/capacity`
- Назначение: capacity view по муфте.
- Возвращает: `MuffleCapacityRead`.
- Доступ: `Designer`.

### `POST /api/network/plan`
- Назначение: сохранить план дома.
- Принимает: JSON.
- Обязательные поля:
  - `address`
  - `entrances_count`
  - `floors_count`
  - `flats_per_floor`
- Необязательные поля:
  - `tender_id`
  - `city`
  - `servicing_org_name`
  - `servicing_org_phone`
  - `floor_height_m`
  - `panel_every_n_floors`
  - `distance_from_muffle_m`
  - `cable_reserve_pct`
  - `muffle_id`
  - `selected_fibers`
- Пишет в: `buildings`, `tasks`, `task_steps`, `warehouse_requests`, `warehouse_request_items`, `fibers`.
- Возвращает: `NetworkPlanRead`.
- Доступ: `Designer`.

## Tenders

### `GET /api/tenders`
### `POST /api/tenders`
### `GET /api/tenders/{tender_id}`
### `PATCH /api/tenders/{tender_id}/status`
### `GET /api/tenders/{tender_id}/dashboard`
### `POST /api/tenders/{tender_id}/complete`
- Назначение: CRUD/контроль жизненного цикла тендеров.
- Основные обязательные поля для `POST /api/tenders`:
  - `name`
- Необязательные поля:
  - `customer`
  - `city`
  - `deadline`
- Для `PATCH .../status` обязательное поле:
  - `status`
- Пишет в: `tenders`.
- Возвращает: `TenderOverview`, `TenderDashboardRead` или `TenderCompleteRead`.
- Доступ: `Designer`.

## Warehouse

### `GET /api/stock`
- Назначение: остатки склада.
- Возвращает: `list[StockItemRead]`.
- Доступ: `Warehouse`, `Designer`.

### `GET /api/stock/transactions`
- Назначение: история движений.
- Возвращает: `list[StockTransactionRead]`.
- Доступ: `Warehouse`.

### `POST /api/stock/adjust`
- Назначение: ручная корректировка остатков.
- Принимает: JSON.
- Обязательные поля:
  - `stock_item_id`
  - `delta`
  - `reason`
- Пишет в: `stock_items`, `stock_transactions`.
- Возвращает: `StockItemRead`.
- Доступ: `Warehouse`.

### `GET /api/warehouse/requests`
- Назначение: заявки на выдачу со склада.
- Возвращает: `list[WarehouseRequestRead]`.
- Доступ: `Warehouse`.

### `POST /api/warehouse/requests`
- Назначение: создать заявку склада вручную.
- Принимает: JSON.
- Обязательные поля:
  - `items`
- Необязательные поля:
  - `building_id`
  - `task_id`
  - `notes`
- Пишет в: `warehouse_requests`, `warehouse_request_items`.
- Возвращает: `WarehouseRequestRead`.
- Доступ: `Warehouse`.

### `POST /api/warehouse/requests/{request_id}/fulfill`
- Назначение: выдать материалы по заявке.
- Принимает: JSON.
- Обязательные поля:
  - `items`
- Для каждого item обязательные поля:
  - `item_id`
  - `fulfilled_qty`
- Пишет в: `warehouse_requests`, `warehouse_request_items`, `stock_items`, `stock_transactions`.
- Возвращает: `WarehouseRequestRead`.
- Доступ: `Warehouse`.
