CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Synthetic SECS/GEM-style equipment telemetry (Phase 3 prep).
-- Empty on creation; a synthetic-log generator (Plans.md 3.1) backfills rows later.
CREATE TABLE IF NOT EXISTS equipment_telemetry (
    time TIMESTAMPTZ NOT NULL,
    wafer_id TEXT NOT NULL,
    defect_class TEXT,
    equipment_id TEXT,
    param TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('equipment_telemetry', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_equipment_telemetry_wafer ON equipment_telemetry (wafer_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_telemetry_defect ON equipment_telemetry (defect_class, time DESC);
