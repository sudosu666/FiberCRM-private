-- Equivalents of the plan tables; used for reference or manual migrations.
-- Enums / types
CREATE TYPE user_role AS ENUM ('Designer', 'Dispatcher', 'Builder', 'Welder', 'Connector', 'Warehouse');
CREATE TYPE tender_status AS ENUM ('new', 'planning', 'in_progress', 'completed');
CREATE TYPE task_type AS ENUM ('construction', 'welding', 'connection');
CREATE TYPE task_status AS ENUM ('pending', 'assigned', 'in_progress', 'completed', 'canceled');

-- Main tables
CREATE TABLE tenders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    customer VARCHAR(100) DEFAULT 'Vodafone Ukraine',
    status tender_status DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

CREATE TABLE buildings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tender_id UUID REFERENCES tenders(id),
    address TEXT NOT NULL,
    entrances_count INT NOT NULL,
    floors_count INT NOT NULL,
    flats_per_floor INT NOT NULL,
    distance_from_muffle FLOAT,
    infrastructure_status VARCHAR(20) DEFAULT 'planned'
);

CREATE TABLE muffles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coordinate_lat DOUBLE PRECISION,
    coordinate_lon DOUBLE PRECISION,
    capacity INT DEFAULT 16
);

CREATE TABLE fibers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    muffle_id UUID REFERENCES muffles(id),
    fiber_number INT NOT NULL,
    status VARCHAR(20) DEFAULT 'free',
    connected_building_id UUID REFERENCES buildings(id)
);

CREATE TABLE brigades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(80) NOT NULL,
    role VARCHAR(32) NOT NULL,
    members INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type task_type NOT NULL,
    status task_status DEFAULT 'pending',
    building_id UUID REFERENCES buildings(id),
    brigade_id UUID REFERENCES brigades(id),
    priority INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
