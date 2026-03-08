-- ═══════════════════════════════════════════════════════════════════
-- FiberOps CRM — Повна схема БД
-- PostgreSQL 16
-- ═══════════════════════════════════════════════════════════════════

-- ── ENUM ТИПИ ────────────────────────────────────────────────────
CREATE TYPE user_role        AS ENUM ('Designer', 'Dispatcher', 'ConnectionDispatcher', 'Builder', 'Welder', 'Connector', 'Warehouse');
CREATE TYPE tender_status    AS ENUM ('new', 'planning', 'in_progress', 'completed');
CREATE TYPE task_type        AS ENUM ('construction', 'welding', 'connection');
CREATE TYPE task_status      AS ENUM ('pending', 'assigned', 'in_progress', 'on_hold', 'completed', 'canceled');
CREATE TYPE fiber_status     AS ENUM ('free', 'reserved', 'busy');
CREATE TYPE port_status      AS ENUM ('free', 'reserved', 'active', 'faulty');
CREATE TYPE infra_status     AS ENUM ('planned', 'in_progress', 'completed');
CREATE TYPE request_status   AS ENUM ('pending', 'fulfilled', 'partial', 'rejected');
CREATE TYPE subscriber_request_status AS ENUM ('new', 'scheduled', 'in_progress', 'completed', 'postponed', 'canceled', 'no_access', 'technical_issue');
CREATE TYPE arrival_window AS ENUM ('before_lunch', 'after_lunch');


-- ═══════════════════════════════════════════════════════════════════
-- КОРИСТУВАЧІ ТА БРИГАДИ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE users (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(150) NOT NULL,
    phone        VARCHAR(20) UNIQUE,
    email        VARCHAR(150) UNIQUE,
    role         user_role NOT NULL,
    additional_roles TEXT,
    password_hash TEXT NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE brigades (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(100) NOT NULL,          -- "Бригада Б-1"
    type         task_type NOT NULL,             -- construction / welding / connection
    foreman_id   UUID REFERENCES users(id),      -- legacy-поле, поточна цільова модель зменшує його значення
    is_active    BOOLEAN DEFAULT TRUE
);

-- Склад бригади (хто входить)
CREATE TABLE brigade_members (
    brigade_id   UUID REFERENCES brigades(id) ON DELETE CASCADE,
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (brigade_id, user_id)
);


-- ═══════════════════════════════════════════════════════════════════
-- ТЕНДЕРИ ТА БУДИНКИ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE tenders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(255) NOT NULL,
    customer     VARCHAR(100) DEFAULT 'Vodafone Ukraine',
    city         VARCHAR(100),
    status       tender_status DEFAULT 'new',
    deadline     DATE,
    created_at   TIMESTAMP DEFAULT NOW(),
    closed_at    TIMESTAMP
);

CREATE TABLE buildings (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tender_id             UUID REFERENCES tenders(id) ON DELETE CASCADE,

    -- Адреса
    address               TEXT NOT NULL,
    city                  VARCHAR(100),
    servicing_org_name    VARCHAR(150),          -- ЖЕК / ОСББ / керуюча компанія
    servicing_org_phone   VARCHAR(100),

    -- Параметри будинку (вводяться вручну проектувальником)
    entrances_count       INT NOT NULL,
    floors_count          INT NOT NULL,
    flats_per_floor       INT NOT NULL,
    floor_height_m        FLOAT DEFAULT 2.8,     -- висота поверху в метрах
    panel_every_n_floors  INT DEFAULT 5,          -- щиток кожні N поверхів

    -- Кабельна траса
    distance_from_muffle_m  FLOAT,               -- відстань від муфти по трасі, метри
    cable_reserve_pct       INT DEFAULT 15,       -- запас кабелю, %

    -- Точка введення — довільний текст, не моделюємо маршрут
    cable_entry_point     VARCHAR(150),           -- "підвал спільний" / "дах" / "підвал пд.1"
    cable_entry_notes     TEXT,                   -- коментар монтажника після роботи

    -- План vs Факт витрати кабелю
    planned_cable_meters  FLOAT,                  -- розраховується калькулятором
    actual_cable_meters   FLOAT,                  -- вбивається бригадою після роботи

    -- Статус
    infrastructure_status infra_status DEFAULT 'planned',
    completed_at          TIMESTAMP
);

-- Розрахункові показники (генеруються API, не вводяться вручну)
-- panels_count       = entrances_count * CEIL(floors_count / panel_every_n_floors)
-- total_flats        = entrances_count * floors_count * flats_per_floor
-- planned_cable_meters = (entrances_count * floors_count * floor_height_m
--                         + distance_from_muffle_m) * (1 + cable_reserve_pct/100)


-- ═══════════════════════════════════════════════════════════════════
-- ТОПОЛОГІЯ МЕРЕЖІ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE muffles (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(100),                 -- "Муфта M-01 · Польова 1"
    address_note   TEXT,                         -- "Колодязь №4, 80м від будинку"
    coordinate_lat DOUBLE PRECISION,
    coordinate_lon DOUBLE PRECISION,
    capacity       INT DEFAULT 16                -- кількість волокон
);

CREATE TABLE fibers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    muffle_id     UUID REFERENCES muffles(id) ON DELETE CASCADE,
    fiber_number  INT NOT NULL,                  -- 1..16
    status        fiber_status DEFAULT 'free',
    -- НЕ зберігаємо connected_building_id тут —
    -- зв'язок волокна з будинком через panels (одне волокно → сплітер → 32 порти)
    UNIQUE (muffle_id, fiber_number)
);

-- Щитки (розподільні панелі) — 1 щиток на N поверхів у підʼїзді
CREATE TABLE panels (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id   UUID REFERENCES buildings(id) ON DELETE CASCADE,
    fiber_id      UUID REFERENCES fibers(id),    -- яке волокно заведено
    entrance_num  INT NOT NULL,                  -- підʼїзд
    floor_num     INT NOT NULL,                  -- поверх розташування
    label         VARCHAR(50),                   -- "П1-Щ3" (підʼїзд 1, щиток 3)
    splitter_ratio INT DEFAULT 32,               -- 1:32 або 1:64
    installed_at  TIMESTAMP
);

-- Порти сплітера — кінцеві точки для клієнтів
CREATE TABLE ports (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    panel_id      UUID REFERENCES panels(id) ON DELETE CASCADE,
    port_number   INT NOT NULL,                  -- 1..32
    status        port_status DEFAULT 'free',
    UNIQUE (panel_id, port_number)
);


-- ═══════════════════════════════════════════════════════════════════
-- ЗАДАЧІ ТА КРОКИ ВИКОНАННЯ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE tasks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type          task_type NOT NULL,
    status        task_status DEFAULT 'pending',
    priority      INT DEFAULT 0,                 -- 0=normal, 1=urgent

    building_id   UUID REFERENCES buildings(id),
    brigade_id    UUID REFERENCES brigades(id),

    description   TEXT,
    estimated_hours FLOAT,
    is_critical   BOOLEAN DEFAULT FALSE,
    hold_reason   TEXT,

    created_at    TIMESTAMP DEFAULT NOW(),
    assigned_at   TIMESTAMP,
    started_at    TIMESTAMP,
    ended_at      TIMESTAMP,
    completed_at  TIMESTAMP
);

-- Покрокові інструкції для мобільного інтерфейсу бригади
CREATE TABLE task_steps (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID REFERENCES tasks(id) ON DELETE CASCADE,
    step_order    INT NOT NULL,
    title         VARCHAR(200) NOT NULL,         -- "Отримати матеріали на складі"
    hint          TEXT,                          -- "Кабель ОКЛ-16 · 340м, муфта, патч-корди"
    is_done       BOOLEAN DEFAULT FALSE,
    done_at       TIMESTAMP,
    done_by       UUID REFERENCES users(id)
);

-- Фото-звіти від бригади
CREATE TABLE task_reports (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID REFERENCES tasks(id) ON DELETE CASCADE,
    user_id       UUID REFERENCES users(id),
    photo_url     TEXT,                          -- шлях до файлу
    comment       TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);


-- ═══════════════════════════════════════════════════════════════════
-- КЛІЄНТИ ТА ПІДКЛЮЧЕННЯ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE client_connections (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    port_id       UUID REFERENCES ports(id),
    full_name     VARCHAR(200),
    flat_number   INT,
    phone         VARCHAR(20),
    status        VARCHAR(30) DEFAULT 'pending', -- pending/active/suspended
    connected_at  TIMESTAMP,
    task_id       UUID REFERENCES tasks(id)      -- задача підключення
);

CREATE TABLE subscriber_requests (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id       UUID REFERENCES buildings(id) ON DELETE CASCADE,
    flat_number       INT NOT NULL,
    customer_name     VARCHAR(200) NOT NULL,
    phone             VARCHAR(20) NOT NULL,
    notes             TEXT,
    status            subscriber_request_status DEFAULT 'new',
    registered_at     TIMESTAMP DEFAULT NOW(),
    deadline_at       TIMESTAMP NOT NULL,
    scheduled_date    DATE,
    arrival_window    arrival_window,
    assigned_user_id  UUID REFERENCES users(id),
    completed_at      TIMESTAMP
);


-- ═══════════════════════════════════════════════════════════════════
-- СКЛАД ТА МАТЕРІАЛИ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE stock_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(150) NOT NULL,          -- "Кабель ОКЛ-16"
    unit          VARCHAR(20) NOT NULL,            -- "м", "шт"
    quantity      FLOAT DEFAULT 0,
    min_quantity  FLOAT DEFAULT 0,                 -- поріг попередження
    updated_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE stock_transactions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id UUID REFERENCES stock_items(id),
    delta         FLOAT NOT NULL,                  -- + надходження, - видача
    reason        VARCHAR(100),                    -- "видача по заявці" / "коригування"
    task_id       UUID REFERENCES tasks(id),       -- до якої задачі прив'язано
    user_id       UUID REFERENCES users(id),       -- хто провів
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE warehouse_requests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_by  UUID REFERENCES users(id),
    task_id       UUID REFERENCES tasks(id),
    building_id   UUID REFERENCES buildings(id),
    status        request_status DEFAULT 'pending',
    notes         TEXT,
    created_at    TIMESTAMP DEFAULT NOW(),
    fulfilled_at  TIMESTAMP
);

CREATE TABLE warehouse_request_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id    UUID REFERENCES warehouse_requests(id) ON DELETE CASCADE,
    stock_item_id UUID REFERENCES stock_items(id),
    planned_qty   FLOAT NOT NULL,                  -- скільки запросили
    fulfilled_qty FLOAT                            -- скільки фактично видали
);


-- ═══════════════════════════════════════════════════════════════════
-- ОПЕРАЦІЙНІ КОМЕНТАРІ ТА КОНТАКТИ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE ops_contacts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                UUID REFERENCES tasks(id) ON DELETE CASCADE,
    subscriber_request_id  UUID REFERENCES subscriber_requests(id) ON DELETE CASCADE,
    title                  VARCHAR(120) NOT NULL, -- "ЖЕК", "ОСББ", "Консьєрж", "Клієнт"
    full_name              VARCHAR(200),
    phone                  VARCHAR(50) NOT NULL,
    notes                  TEXT,
    created_at             TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ops_comments (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id            UUID REFERENCES buildings(id) ON DELETE CASCADE,
    task_id                UUID REFERENCES tasks(id) ON DELETE CASCADE,
    subscriber_request_id  UUID REFERENCES subscriber_requests(id) ON DELETE CASCADE,
    author_id              UUID REFERENCES users(id),
    comment_type           VARCHAR(50) NOT NULL,  -- note/design_note/postpone/warning/access_note
    body                   TEXT NOT NULL,
    role_tags              TEXT,
    created_at             TIMESTAMP DEFAULT NOW()
);


-- ═══════════════════════════════════════════════════════════════════
-- ЧАТ ТА СПОВІЩЕННЯ
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE messages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID REFERENCES tasks(id) ON DELETE CASCADE,
    sender_id     UUID REFERENCES users(id),
    body          TEXT,
    photo_url     TEXT,                            -- опціональне фото в чаті
    is_read       BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE notifications (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
    title         VARCHAR(200) NOT NULL,
    body          TEXT,
    is_read       BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Push-підписки для Web Push API (PWA бригади)
CREATE TABLE push_subscriptions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
    endpoint      TEXT NOT NULL,
    p256dh        TEXT NOT NULL,
    auth          TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW()
);


-- ═══════════════════════════════════════════════════════════════════
-- ІНДЕКСИ
-- ═══════════════════════════════════════════════════════════════════

CREATE INDEX idx_buildings_tender     ON buildings(tender_id);
CREATE INDEX idx_fibers_muffle        ON fibers(muffle_id);
CREATE INDEX idx_panels_building      ON panels(building_id);
CREATE INDEX idx_panels_fiber         ON panels(fiber_id);
CREATE INDEX idx_ports_panel          ON ports(panel_id);
CREATE INDEX idx_tasks_building       ON tasks(building_id);
CREATE INDEX idx_tasks_brigade        ON tasks(brigade_id);
CREATE INDEX idx_tasks_status         ON tasks(status);
CREATE INDEX idx_task_steps_task      ON task_steps(task_id);
CREATE INDEX idx_subscriber_req_building ON subscriber_requests(building_id);
CREATE INDEX idx_subscriber_req_status   ON subscriber_requests(status);
CREATE INDEX idx_ops_contacts_task       ON ops_contacts(task_id);
CREATE INDEX idx_ops_contacts_subscriber ON ops_contacts(subscriber_request_id);
CREATE INDEX idx_ops_comments_building   ON ops_comments(building_id);
CREATE INDEX idx_ops_comments_task       ON ops_comments(task_id);
CREATE INDEX idx_ops_comments_subscriber ON ops_comments(subscriber_request_id);
CREATE INDEX idx_messages_task        ON messages(task_id);
CREATE INDEX idx_notifications_user   ON notifications(user_id, is_read);
CREATE INDEX idx_stock_tx_item        ON stock_transactions(stock_item_id);
CREATE INDEX idx_ports_status         ON ports(status);
