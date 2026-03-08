# FiberOps Entities Inventory

Краткий каталог основных сущностей системы. Для каждой сущности указано назначение, поля, обязательность и связи.

## `users`
- Назначение: пользователи системы.
- Поля:
  - `id` UUID, обязательный, PK
  - `name` string, обязательный
  - `phone` string, обязательный, уникальный, используется как личный номер и логин
  - `email` string, необязательный
  - `role` enum `UserRole`, обязательный
  - `additional_roles` string, необязательный, CSV допролей
  - `password_hash` text, обязательный
  - `is_active` boolean, обязательный
  - `created_at` datetime, обязательный
- Связи:
  - `brigade_members`
  - `task_steps_done`
  - `task_reports`
  - `work_logs`
  - `notifications`
  - `push_subscriptions`

## `brigades`
- Назначение: группа исполнителей по типу работ.
- Поля:
  - `id` UUID, PK
  - `name` string, обязательный
  - `type` enum `TaskType`, обязательный
  - `foreman_id` UUID, необязательный, legacy-поле
  - `is_active` boolean, обязательный
- Связи:
  - `brigade_members`
  - `tasks`

## `brigade_members`
- Назначение: membership пользователей в бригадах.
- Поля:
  - `brigade_id` UUID, обязательный, PK/FK
  - `user_id` UUID, обязательный, PK/FK

## `tenders`
- Назначение: верхнеуровневый строительный входной поток.
- Поля:
  - `id` UUID, PK
  - `name` string, обязательный
  - `customer` string, обязательный
  - `city` string, необязательный
  - `status` enum `TenderStatus`, обязательный
  - `deadline` date, необязательный
  - `created_at` datetime, обязательный
  - `closed_at` datetime, необязательный
- Связи:
  - `buildings`

## `buildings`
- Назначение: реестр домов последней мили.
- Поля:
  - `id` UUID, PK
  - `tender_id` UUID, обязательный
  - `address` text, обязательный
  - `city` string, необязательный
  - `servicing_org_name` string, необязательный, ЖЭК/ОСББ
  - `servicing_org_phone` string, необязательный
  - `entrances_count` int, обязательный
  - `floors_count` int, обязательный
  - `flats_per_floor` int, обязательный
  - `floor_height_m` float, обязательный
  - `panel_every_n_floors` int, обязательный
  - `distance_from_muffle_m` float, необязательный
  - `cable_reserve_pct` int, обязательный
  - `cable_entry_point` string, необязательный
  - `cable_entry_notes` text, необязательный
  - `planned_cable_meters` float, необязательный
  - `actual_cable_meters` float, необязательный
  - `infrastructure_status` enum `InfraStatus`, обязательный
  - `completed_at` datetime, необязательный
- Связи:
  - `tender`
  - `tasks`
  - `panels`
  - `notes`
  - `comments`
  - `subscriber_requests`

## `muffles`
- Назначение: муфты сети.
- Поля:
  - `id` UUID, PK
  - `name` string, необязательный
  - `address_note` text, необязательный
  - `coordinate_lat` float, необязательный
  - `coordinate_lon` float, необязательный
  - `capacity` int, обязательный
- Связи:
  - `fibers`

## `fibers`
- Назначение: волокна внутри муфты.
- Поля:
  - `id` UUID, PK
  - `muffle_id` UUID, обязательный
  - `fiber_number` int, обязательный
  - `status` enum `FiberStatus`, обязательный
- Связи:
  - `muffle`
  - `panels`

## `panels`
- Назначение: щитки/распределительные панели в доме.
- Поля:
  - `id` UUID, PK
  - `building_id` UUID, обязательный
  - `fiber_id` UUID, необязательный
  - `entrance_num` int, обязательный
  - `floor_num` int, обязательный
  - `label` string, необязательный
  - `splitter_ratio` int, обязательный
  - `installed_at` datetime, необязательный
- Связи:
  - `building`
  - `fiber`
  - `ports`

## `ports`
- Назначение: клиентские порты сплиттера.
- Поля:
  - `id` UUID, PK
  - `panel_id` UUID, обязательный
  - `port_number` int, обязательный
  - `status` enum `PortStatus`, обязательный
- Связи:
  - `panel`

## `tasks`
- Назначение: строительные и полевые задачи.
- Поля:
  - `id` UUID, PK
  - `type` enum `TaskType`, обязательный
  - `status` enum `TaskStatus`, обязательный
  - `priority` int, обязательный
  - `building_id` UUID, необязательный
  - `brigade_id` UUID, необязательный, текущая модель назначения
  - `description` text, необязательный
  - `estimated_hours` float, необязательный
  - `is_critical` boolean, обязательный
  - `hold_reason` text, необязательный
  - `postponed_reason` text, legacy transitional field
  - `postponed_at` datetime, legacy transitional field
  - `created_at` datetime, обязательный
  - `assigned_at` datetime, необязательный
  - `started_at` datetime, необязательный
  - `ended_at` datetime, необязательный
  - `completed_at` datetime, необязательный
- Связи:
  - `building`
  - `brigade`
  - `steps`
  - `reports`
  - `contacts`
  - `comments`

## `task_steps`
- Назначение: пошаговое исполнение задачи.
- Поля:
  - `id` UUID, PK
  - `task_id` UUID, обязательный
  - `step_order` int, обязательный
  - `title` string, обязательный
  - `hint` text, необязательный
  - `is_done` boolean, обязательный
  - `done_at` datetime, необязательный
  - `done_by` UUID, необязательный
- Связи:
  - `task`
  - `actor`

## `task_reports`
- Назначение: фотоотчёты по задачам.
- Поля:
  - `id` UUID, PK
  - `task_id` UUID, обязательный
  - `user_id` UUID, обязательный
  - `photo_url` text, необязательный
  - `comment` text, необязательный
  - `brigade_id` UUID, необязательный
  - `brigade_name` string, необязательный
  - `created_at` datetime, обязательный

## `subscriber_requests`
- Назначение: одиночные заявки на подключение клиентов.
- Поля:
  - `id` UUID, PK
  - `building_id` UUID, обязательный
  - `flat_number` int, обязательный
  - `customer_name` string, обязательный
  - `phone` string, обязательный
  - `notes` text, необязательный
  - `postponed_reason` text, legacy transitional field
  - `postponed_at` datetime, legacy transitional field
  - `status` enum `SubscriberRequestStatus`, обязательный
  - `registered_at` datetime, обязательный
  - `deadline_at` datetime, обязательный
  - `scheduled_date` date, необязательный
  - `arrival_window` enum `ArrivalWindow`, необязательный
  - `assigned_user_id` UUID, необязательный
  - `completed_at` datetime, необязательный
- Связи:
  - `building`
  - `assigned_user`
  - `contacts`
  - `comments`

## `client_connections`
- Назначение: фактические подключения квартир к портам.
- Поля:
  - `id` UUID, PK
  - `port_id` UUID, обязательный
  - `full_name` string, необязательный
  - `flat_number` int, необязательный
  - `phone` string, необязательный
  - `status` string, обязательный
  - `connected_at` datetime, необязательный
  - `task_id` UUID, необязательный

## `stock_items`
- Назначение: складские позиции.
- Поля:
  - `id` UUID, PK
  - `name` string, обязательный
  - `unit` string, обязательный
  - `quantity` float, обязательный
  - `min_quantity` float, обязательный
  - `updated_at` datetime, обязательный

## `stock_transactions`
- Назначение: история движений склада.
- Поля:
  - `id` UUID, PK
  - `stock_item_id` UUID, обязательный
  - `delta` float, обязательный
  - `reason` string, необязательный
  - `task_id` UUID, необязательный
  - `user_id` UUID, необязательный
  - `created_at` datetime, обязательный

## `warehouse_requests`
- Назначение: заявки на выдачу со склада.
- Поля:
  - `id` UUID, PK
  - `requested_by` UUID, обязательный
  - `task_id` UUID, необязательный
  - `building_id` UUID, необязательный
  - `status` enum `RequestStatus`, обязательный
  - `notes` text, необязательный
  - `created_at` datetime, обязательный
  - `fulfilled_at` datetime, необязательный

## `warehouse_request_items`
- Назначение: позиции внутри складской заявки.
- Поля:
  - `id` UUID, PK
  - `request_id` UUID, обязательный
  - `stock_item_id` UUID, обязательный
  - `planned_qty` float, обязательный
  - `fulfilled_qty` float, необязательный

## `building_notes`
- Назначение: legacy notes по дому.
- Поля:
  - `id` UUID, PK
  - `building_id` UUID, обязательный
  - `author_id` UUID, необязательный
  - `body` text, обязательный
  - `role_tags` text, необязательный
  - `created_at` datetime, обязательный

## `ops_contacts`
- Назначение: отдельные контакты по задаче или заявке.
- Поля:
  - `id` UUID, PK
  - `task_id` UUID, необязательный
  - `subscriber_request_id` UUID, необязательный
  - `title` string, обязательный
  - `full_name` string, необязательный
  - `phone` string, обязательный
  - `notes` text, необязательный
  - `created_at` datetime, обязательный

## `ops_comments`
- Назначение: единый журнал комментариев/заметок/переносов.
- Поля:
  - `id` UUID, PK
  - `building_id` UUID, необязательный
  - `task_id` UUID, необязательный
  - `subscriber_request_id` UUID, необязательный
  - `author_id` UUID, необязательный
  - `comment_type` string, обязательный
  - `body` text, обязательный
  - `role_tags` text, необязательный
  - `created_at` datetime, обязательный
- Типовые `comment_type`:
  - `note`
  - `design_note`
  - `postpone`
  - `warning`
  - `access_note`

## `messages`
- Назначение: чат по задачам.

## `notifications`
- Назначение: уведомления.

## `push_subscriptions`
- Назначение: push subscriptions для PWA.
