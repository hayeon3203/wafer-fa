# Ralph Progress Log

Started: 2026-07-22
Task: Phase 3 (합성 장비 로그 상관관계) — see Plans.md for full project history through Phase 2.5.

## Codebase Patterns

- Package lives in `src/daol_fascope/`, tests in `tests/`. Run with `PYTHONPATH=src` set (see `.venv` at repo root).
- Full task history and design decisions (grilling sessions, ADRs) live in `Plans.md` and `docs/adr/*.md` — read those before Phase 3 work, not just this file.
- ThingsBoard device telemetry pattern: `src/daol_fascope/telemetry.py`, swallow network errors, return False (never break the demo).
- Existing TimescaleDB container `daol-fascope-timescaledb` (docker-compose.yml, localhost:5433, db/user `wafer_fa`) has an empty hypertable `equipment_telemetry` (time/wafer_id/defect_class/equipment_id/param/value) pre-provisioned for Phase 3.

## Key Files

- `Plans.md` — authoritative task tracker for this project (cc:TODO/cc:완료 markers), source of truth over this file for anything already decided.
- `CONTEXT.md` — domain glossary.
- `docker-compose.yml` — ThingsBoard + TimescaleDB services.

---
