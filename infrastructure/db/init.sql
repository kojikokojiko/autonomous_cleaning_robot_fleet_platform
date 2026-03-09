-- RobotOps Platform Database Schema

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Robots Table
-- ============================================================
CREATE TABLE IF NOT EXISTS robots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    robot_id        VARCHAR(64) UNIQUE NOT NULL,
    name            VARCHAR(128) NOT NULL,
    facility        VARCHAR(128),
    model           VARCHAR(64),
    firmware_version VARCHAR(32),
    status          VARCHAR(32) NOT NULL DEFAULT 'offline',
        -- offline | idle | cleaning | charging | docked | error | ota_update
    battery_level   FLOAT,
    position_x      FLOAT,
    position_y      FLOAT,
    position_floor  INTEGER DEFAULT 1,
    last_seen       TIMESTAMPTZ,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_robots_status ON robots(status);
CREATE INDEX idx_robots_facility ON robots(facility);

-- ============================================================
-- Missions Table
-- ============================================================
CREATE TABLE IF NOT EXISTS missions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(128) NOT NULL,
    facility        VARCHAR(128),
    zone            VARCHAR(64) NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 5, -- 1 (highest) - 10 (lowest)
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
        -- pending | assigned | in_progress | completed | failed | cancelled
    assigned_robot  UUID REFERENCES robots(id),
    scheduled_at    TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    coverage_pct    FLOAT DEFAULT 0.0,
    created_by      VARCHAR(128),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_missions_status ON missions(status);
CREATE INDEX idx_missions_scheduled_at ON missions(scheduled_at);
CREATE INDEX idx_missions_assigned_robot ON missions(assigned_robot);

-- ============================================================
-- Telemetry Table (TimescaleDB hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS telemetry (
    time            TIMESTAMPTZ NOT NULL,
    robot_id        VARCHAR(64) NOT NULL,
    battery_level   FLOAT,
    position_x      FLOAT,
    position_y      FLOAT,
    position_floor  INTEGER,
    nav_status      VARCHAR(32),
    motor_load_left  FLOAT,
    motor_load_right FLOAT,
    sensor_health   JSONB,
    mission_id      UUID,
    mission_progress FLOAT,
    speed           FLOAT
);

SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);
CREATE INDEX idx_telemetry_robot_id ON telemetry(robot_id, time DESC);

-- Retention policy: keep 90 days of telemetry
SELECT add_retention_policy('telemetry', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================
-- Events Table
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    robot_id        VARCHAR(64) NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
        -- RobotBatteryLow | RobotStuck | CollisionDetected | MissionStarted | MissionCompleted
    severity        VARCHAR(16) NOT NULL DEFAULT 'info',
        -- info | warning | error | critical
    payload         JSONB,
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by VARCHAR(128),
    acknowledged_at TIMESTAMPTZ,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_robot_id ON events(robot_id, occurred_at DESC);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_severity ON events(severity);
CREATE INDEX idx_events_acknowledged ON events(acknowledged);

-- ============================================================
-- Firmware Table
-- ============================================================
CREATE TABLE IF NOT EXISTS firmware (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version         VARCHAR(32) UNIQUE NOT NULL,
    s3_key          VARCHAR(512) NOT NULL,
    checksum_sha256  VARCHAR(64) NOT NULL,
    file_size_bytes BIGINT,
    release_notes   TEXT,
    is_stable       BOOLEAN NOT NULL DEFAULT FALSE,
    uploaded_by     VARCHAR(128),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- OTA Jobs Table
-- ============================================================
CREATE TABLE IF NOT EXISTS ota_jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id     UUID NOT NULL REFERENCES firmware(id),
    robot_id        UUID NOT NULL REFERENCES robots(id),
    strategy        VARCHAR(32) NOT NULL DEFAULT 'rolling',
        -- rolling | canary
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
        -- pending | notified | downloading | applying | completed | failed | rolled_back
    attempts        INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ota_jobs_robot_id ON ota_jobs(robot_id);
CREATE INDEX idx_ota_jobs_status ON ota_jobs(status);

-- ============================================================
-- Maps Table
-- ============================================================
CREATE TABLE IF NOT EXISTS maps (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility        VARCHAR(128) NOT NULL,
    floor           INTEGER NOT NULL DEFAULT 1,
    name            VARCHAR(128),
    s3_key          VARCHAR(512) NOT NULL,
    width           INTEGER,
    height          INTEGER,
    resolution      FLOAT, -- meters per pixel
    origin_x        FLOAT,
    origin_y        FLOAT,
    zones           JSONB, -- zone definitions [{name, polygon_points}]
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_maps_facility_floor ON maps(facility, floor) WHERE is_active = TRUE;

-- ============================================================
-- Digital Twin Snapshots (audit log)
-- ============================================================
CREATE TABLE IF NOT EXISTS twin_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    robot_id        VARCHAR(64) NOT NULL,
    state           JSONB NOT NULL,
    snapshotted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_twin_snapshots_robot_id ON twin_snapshots(robot_id, snapshotted_at DESC);

-- ============================================================
-- Command History Table
-- ============================================================
CREATE TABLE IF NOT EXISTS commands (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    robot_id        VARCHAR(64) NOT NULL,
    command_type    VARCHAR(64) NOT NULL,
        -- start_mission | pause_mission | return_to_dock | emergency_stop
    payload         JSONB,
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
        -- pending | sent | acknowledged | failed | timed_out
    issued_by       VARCHAR(128),
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    retry_count     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_commands_robot_id ON commands(robot_id, issued_at DESC);
CREATE INDEX idx_commands_status ON commands(status);
