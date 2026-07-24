# Kafka Streaming Smoketest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream synthetic wafer equipment-sensor snapshots through Kafka (producer → broker → consumer) that dual-writes to TimescaleDB + ThingsBoard, printing millisecond-level throughput/latency stats so the user can confirm real-time processing actually happens.

**Architecture:** Single-broker KRaft-mode `apache/kafka` container added to the existing `docker-compose.yml`. A producer script replays the existing SECOM-derived 562-sensor synthetic sampler (`equipment_log.py`, already built for Phase 3.1) one wafer per Kafka message, unthrottled. A consumer script reads each message, writes the 562 rows into the existing `equipment_telemetry` TimescaleDB table (COPY, same pattern as `build_equipment_log.py`) and POSTs the same 562 values as one ThingsBoard telemetry payload, timing each stage in milliseconds and printing a summary after a fixed wafer count.

**Tech Stack:** `confluent-kafka` (librdkafka bindings), existing `psycopg`/`requests`/`pandas`/`numpy` deps, `apache/kafka` Docker image (KRaft, no ZooKeeper).

## Global Constraints

- Kafka image: `apache/kafka` (official Apache image), KRaft single-broker, no ZooKeeper.
- Topic: `equipment-telemetry-stream`, 1 partition.
- Producer: one Kafka message = one wafer's full 562 `(param, value)` snapshot. No throttling — max speed.
- `wafer_id` for streamed data: `f"STREAM_{run_id}_{i}"` — must never collide with the 172,950 real `{lot_id}_{wafer_index}` ids already in `equipment_telemetry` from Phase 3.1's batch load.
- Consumer dual-writes every message to (a) TimescaleDB `equipment_telemetry` (existing schema, no migration) and (b) ThingsBoard device telemetry API, **one POST per wafer** (not per sensor).
- No new ThingsBoard widget. Performance numbers (throughput, end-to-end/DB/ThingsBoard latency in ms, avg + p99) print to console only, after a fixed `--wafers N` count is processed.
- Consumer group id is randomized per run + `auto.offset.reset=latest` — consumer must be started before the producer (this is intentional: it's testing a live stream, not draining a backlog).
- Spec: `docs/superpowers/specs/2026-07-24-kafka-streaming-smoketest-design.md`.

---

### Task 1: Kafka broker in docker-compose + `confluent-kafka` dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: a reachable Kafka broker at `localhost:9092` for all later tasks.

- [ ] **Step 1: Add the dependency**

Append to `requirements.txt`:

```
confluent-kafka
```

- [ ] **Step 2: Install it**

Run: `pip install confluent-kafka`
Expected: installs successfully (wheel available for linux x86_64/arm64, no compiler needed).

- [ ] **Step 3: Add the Kafka service to docker-compose.yml**

In `/home/admin/daol-fascope/docker-compose.yml`, add this service under `services:` (after the `thingsboard` service, before `waferscope-nginx`):

```yaml
  kafka:
    image: apache/kafka:latest
    container_name: daol-fascope-kafka
    restart: unless-stopped
    ports:
      - "9092:9092"
    environment:
      - KAFKA_NODE_ID=1
      - KAFKA_PROCESS_ROLES=broker,controller
      - KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
      - KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092
      - KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER
      - KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093
      - KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      - KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT
      - KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
      - CLUSTER_ID=MkU3OEVBNTcwNTJENDM2Qk
```

- [ ] **Step 4: Start it and verify it's reachable**

Run: `docker compose up -d kafka && sleep 10 && docker compose logs kafka --tail 20`
Expected: log lines showing `Kafka Server started` (no restart loop, no error stack trace).

Run:
```bash
python3 -c "
from confluent_kafka.admin import AdminClient
admin = AdminClient({'bootstrap.servers': 'localhost:9092'})
print(admin.list_topics(timeout=5).brokers)
"
```
Expected: prints a dict with one broker entry (id 1), no exception.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt docker-compose.yml
git commit -m "feat: add apache/kafka KRaft broker + confluent-kafka dependency"
```

---

### Task 2: Message schema (`kafka_common.py`)

**Files:**
- Create: `src/daol_fascope/kafka_common.py`
- Test: `tests/test_kafka_common.py`

**Interfaces:**
- Consumes: nothing (stdlib `json`, `os`, `time` only).
- Produces: `TOPIC: str`, `KAFKA_BOOTSTRAP_SERVERS: str`, `build_message(wafer_id: str, defect_class: str, readings: list[tuple[str, float]]) -> bytes`, `parse_message(raw: bytes) -> dict` (keys: `wafer_id`, `defect_class`, `produced_at_ms`, `readings`) — used by Task 4 (producer) and Task 5 (consumer).

- [ ] **Step 1: Write the failing test**

Create `tests/test_kafka_common.py`:

```python
from daol_fascope.kafka_common import build_message, parse_message


def test_build_and_parse_message_roundtrip():
    readings = [("feature_0", 1.23), ("feature_1", -4.5)]
    raw = build_message("STREAM_run1_0", "Center", readings)
    parsed = parse_message(raw)
    assert parsed["wafer_id"] == "STREAM_run1_0"
    assert parsed["defect_class"] == "Center"
    assert parsed["readings"] == [list(r) for r in readings]
    assert isinstance(parsed["produced_at_ms"], int)


def test_build_message_returns_bytes():
    raw = build_message("w1", "none", [("feature_0", 1.0)])
    assert isinstance(raw, bytes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_kafka_common.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daol_fascope.kafka_common'`

- [ ] **Step 3: Write the implementation**

Create `src/daol_fascope/kafka_common.py`:

```python
"""Shared wire format for the Kafka equipment-telemetry-stream smoke test
(docs/superpowers/specs/2026-07-24-kafka-streaming-smoketest-design.md).
Producer and consumer both import this so the message schema lives in one
place instead of drifting between the two scripts.
"""
import json
import os
import time

TOPIC = "equipment-telemetry-stream"
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def build_message(wafer_id: str, defect_class: str, readings: list[tuple[str, float]]) -> bytes:
    payload = {
        "wafer_id": wafer_id,
        "defect_class": defect_class,
        "produced_at_ms": int(time.time() * 1000),
        "readings": readings,
    }
    return json.dumps(payload).encode("utf-8")


def parse_message(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_kafka_common.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daol_fascope/kafka_common.py tests/test_kafka_common.py
git commit -m "feat: add Kafka message schema (kafka_common)"
```

---

### Task 3: ThingsBoard snapshot telemetry (`telemetry.send_equipment_snapshot`)

**Files:**
- Modify: `src/daol_fascope/telemetry.py`
- Test: `tests/test_telemetry.py`

**Interfaces:**
- Consumes: existing `_post(payload: dict) -> bool` in the same file.
- Produces: `send_equipment_snapshot(readings: list[tuple[str, float]]) -> bool` — used by Task 5 (consumer).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_telemetry.py`:

```python
def test_send_equipment_snapshot_posts_one_payload_per_wafer(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    monkeypatch.setattr(telemetry, "THINGSBOARD_URL", "http://tb.local")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        result = telemetry.send_equipment_snapshot([("feature_0", 1.5), ("feature_1", -2.0)])
    assert result is True
    assert mock_post.call_count == 1
    url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert url == "http://tb.local/api/v1/tok123/telemetry"
    assert kwargs["json"] == {"feature_0": 1.5, "feature_1": -2.0}


def test_send_equipment_snapshot_no_token_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "")
    assert telemetry.send_equipment_snapshot([("feature_0", 1.0)]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_telemetry.py -v -k equipment_snapshot`
Expected: FAIL with `AttributeError: module 'daol_fascope.telemetry' has no attribute 'send_equipment_snapshot'`

- [ ] **Step 3: Write the implementation**

Append to `src/daol_fascope/telemetry.py`:

```python
def send_equipment_snapshot(readings: list[tuple[str, float]]) -> bool:
    """POST one wafer's full sensor snapshot as a single telemetry payload
    (Kafka streaming smoketest, 2026-07-24 design) -- one POST per wafer,
    not one per sensor, so ThingsBoard's HTTP round-trip time doesn't become
    the bottleneck the smoke test is trying to measure."""
    payload = {param: value for param, value in readings}
    return _post(payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_telemetry.py -v`
Expected: PASS (all tests in file, including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add src/daol_fascope/telemetry.py tests/test_telemetry.py
git commit -m "feat: add send_equipment_snapshot for Kafka consumer dual-write"
```

---

### Task 4: Producer (`kafka_producer.py`)

**Files:**
- Create: `src/daol_fascope/kafka_producer.py`
- Test: `tests/test_kafka_producer.py`

**Interfaces:**
- Consumes: `daol_fascope.build_equipment_log.{MANIFEST, build_assignments}`, `daol_fascope.equipment_log.sample_wafer_readings(assignments, defect_class, rng) -> list[tuple[str, float]]`, `daol_fascope.kafka_common.{TOPIC, KAFKA_BOOTSTRAP_SERVERS, build_message}`.
- Produces: `pick_defect_class(labels: np.ndarray, rng: np.random.Generator) -> str` (unit tested), `run(wafers: int, run_id: str) -> None`, CLI entrypoint `main()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_kafka_producer.py`:

```python
import numpy as np

from daol_fascope.kafka_producer import pick_defect_class


def test_pick_defect_class_returns_value_from_labels():
    rng = np.random.default_rng(0)
    labels = np.array(["Center", "none", "Scratch"])
    result = pick_defect_class(labels, rng)
    assert result in labels


def test_pick_defect_class_is_deterministic_for_seeded_rng():
    labels = np.array(["Center", "none", "Scratch", "Donut"])
    first = pick_defect_class(labels, np.random.default_rng(42))
    second = pick_defect_class(labels, np.random.default_rng(42))
    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_kafka_producer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daol_fascope.kafka_producer'`

- [ ] **Step 3: Write the implementation**

Create `src/daol_fascope/kafka_producer.py`:

```python
"""Kafka producer for the equipment-telemetry-stream smoke test (see
docs/superpowers/specs/2026-07-24-kafka-streaming-smoketest-design.md).
Publishes one message per synthetic wafer (562-sensor snapshot, reusing
Phase 3.1's SECOM-derived sampler), unthrottled, until --wafers is reached.

Run: PYTHONPATH=src python -m daol_fascope.kafka_producer --wafers 1000

Start the consumer (kafka_consumer.py) BEFORE running this -- the consumer
group resets to "latest", so it only sees messages produced after it
subscribes.
"""
import argparse
import time
import uuid

import numpy as np
import pandas as pd
from confluent_kafka import Producer

from daol_fascope.build_equipment_log import MANIFEST, build_assignments
from daol_fascope.equipment_log import sample_wafer_readings
from daol_fascope.kafka_common import KAFKA_BOOTSTRAP_SERVERS, TOPIC, build_message


def pick_defect_class(labels: np.ndarray, rng: np.random.Generator) -> str:
    return rng.choice(labels)


def run(wafers: int, run_id: str) -> None:
    print("loading SECOM + manifest ...")
    assignments = build_assignments()
    labels = pd.read_csv(MANIFEST)["label"].to_numpy()
    rng = np.random.default_rng()

    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
    start = time.monotonic()
    for i in range(wafers):
        defect_class = pick_defect_class(labels, rng)
        wafer_id = f"STREAM_{run_id}_{i}"
        readings = sample_wafer_readings(assignments, defect_class, rng)
        message = build_message(wafer_id, defect_class, readings)
        producer.produce(TOPIC, key=wafer_id.encode(), value=message)
        producer.poll(0)
    producer.flush()
    elapsed = time.monotonic() - start
    print(f"produced {wafers} wafers in {elapsed:.2f}s ({wafers / elapsed:.1f} wafers/sec)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wafers", type=int, default=1000)
    args = parser.parse_args()
    run(args.wafers, run_id=uuid.uuid4().hex[:8])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_kafka_producer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daol_fascope/kafka_producer.py tests/test_kafka_producer.py
git commit -m "feat: add Kafka producer for equipment-telemetry-stream smoketest"
```

---

### Task 5: Consumer (`kafka_consumer.py`) + end-to-end verification

**Files:**
- Create: `src/daol_fascope/kafka_consumer.py`
- Test: `tests/test_kafka_consumer.py`

**Interfaces:**
- Consumes: `daol_fascope.kafka_common.{TOPIC, KAFKA_BOOTSTRAP_SERVERS, parse_message}`, `daol_fascope.telemetry.send_equipment_snapshot`.
- Produces: `latency_ms(produced_at_ms: int, consumed_at_ms: int) -> int`, `build_copy_buffer(time_iso: str, wafer_id: str, defect_class: str, readings: list) -> str`, `class Stats` (`.record(e2e_ms, db_ms, tb_ms, tb_ok)`, `.summary() -> dict`, `.print_summary()`), `run(wafers: int) -> None`, CLI entrypoint `main()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_kafka_consumer.py`:

```python
import time

from daol_fascope.kafka_consumer import Stats, build_copy_buffer, latency_ms


def test_latency_ms_computes_difference():
    assert latency_ms(1_000, 1_050) == 50


def test_build_copy_buffer_formats_one_row():
    buf = build_copy_buffer("2026-07-24T00:00:00+00:00", "STREAM_r1_0", "Center", [("feature_0", 1.5)])
    assert buf == "2026-07-24T00:00:00+00:00\tSTREAM_r1_0\tCenter\tfeature_0\tfeature_0\t1.5\n"


def test_build_copy_buffer_formats_multiple_rows():
    buf = build_copy_buffer("t", "w1", "none", [("feature_0", 1.0), ("feature_1", 2.0)])
    assert buf == "t\tw1\tnone\tfeature_0\tfeature_0\t1.0\nt\tw1\tnone\tfeature_1\tfeature_1\t2.0\n"


def test_stats_summary_reports_count_and_avg_latency():
    stats = Stats()
    stats.start = time.monotonic() - 2.0
    for _ in range(10):
        stats.record(e2e_ms=50.0, db_ms=5.0, tb_ms=20.0, tb_ok=True)
    summary = stats.summary()
    assert summary["count"] == 10
    assert summary["e2e_latency"]["avg_ms"] == 50.0
    assert summary["db_latency"]["avg_ms"] == 5.0
    assert summary["tb_latency"]["avg_ms"] == 20.0
    assert summary["tb_failures"] == 0
    assert summary["throughput_wafers_per_sec"] > 0


def test_stats_counts_thingsboard_failures():
    stats = Stats()
    stats.record(e2e_ms=1.0, db_ms=1.0, tb_ms=1.0, tb_ok=False)
    stats.record(e2e_ms=1.0, db_ms=1.0, tb_ms=1.0, tb_ok=True)
    assert stats.summary()["tb_failures"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/test_kafka_consumer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daol_fascope.kafka_consumer'`

- [ ] **Step 3: Write the implementation**

Create `src/daol_fascope/kafka_consumer.py`:

```python
"""Kafka consumer for the equipment-telemetry-stream smoke test -- dual
writes each wafer snapshot to TimescaleDB + ThingsBoard, measuring
end-to-end/DB/ThingsBoard latency in milliseconds and overall throughput.
See docs/superpowers/specs/2026-07-24-kafka-streaming-smoketest-design.md.

Run (start this BEFORE kafka_producer.py -- group offset reset is "latest",
so it only sees messages produced after it subscribes, same as watching a
real live stream rather than draining a backlog):
  PYTHONPATH=src python -m daol_fascope.kafka_consumer --wafers 1000
"""
import argparse
import os
import time
import uuid

import numpy as np
import pandas as pd
import psycopg
from confluent_kafka import Consumer

from daol_fascope import telemetry
from daol_fascope.kafka_common import KAFKA_BOOTSTRAP_SERVERS, TOPIC, parse_message

DB_HOST = os.environ.get("WAFER_FA_DB_HOST", "localhost")
DB_PORT = os.environ.get("WAFER_FA_DB_PORT", "5433")
DB_NAME = os.environ.get("WAFER_FA_DB_NAME", "wafer_fa")
DB_USER = os.environ.get("WAFER_FA_DB_USER", "wafer_fa")
DB_PASSWORD = os.environ.get("WAFER_FA_DB_PASSWORD", "wafer_fa")


def latency_ms(produced_at_ms: int, consumed_at_ms: int) -> int:
    return consumed_at_ms - produced_at_ms


def build_copy_buffer(time_iso: str, wafer_id: str, defect_class: str, readings: list) -> str:
    lines = [
        f"{time_iso}\t{wafer_id}\t{defect_class}\t{param}\t{param}\t{value}"
        for param, value in readings
    ]
    return "\n".join(lines) + "\n"


def insert_snapshot(conn: psycopg.Connection, wafer_id: str, defect_class: str, readings: list) -> None:
    time_iso = pd.Timestamp.now(tz="UTC").isoformat()
    buf = build_copy_buffer(time_iso, wafer_id, defect_class, readings)
    with conn.cursor().copy(
        "COPY equipment_telemetry (time, wafer_id, defect_class, equipment_id, param, value) FROM STDIN"
    ) as copy:
        copy.write(buf)
    conn.commit()


class Stats:
    def __init__(self):
        self.count = 0
        self.e2e_latency_ms = []
        self.db_latency_ms = []
        self.tb_latency_ms = []
        self.tb_failures = 0
        self.start = time.monotonic()

    def record(self, e2e_ms: float, db_ms: float, tb_ms: float, tb_ok: bool) -> None:
        self.count += 1
        self.e2e_latency_ms.append(e2e_ms)
        self.db_latency_ms.append(db_ms)
        self.tb_latency_ms.append(tb_ms)
        if not tb_ok:
            self.tb_failures += 1

    def summary(self) -> dict:
        elapsed = time.monotonic() - self.start

        def stage(xs):
            arr = np.array(xs)
            return {"avg_ms": float(arr.mean()), "p99_ms": float(np.percentile(arr, 99))}

        return {
            "count": self.count,
            "elapsed_sec": elapsed,
            "throughput_wafers_per_sec": self.count / elapsed if elapsed > 0 else 0.0,
            "e2e_latency": stage(self.e2e_latency_ms),
            "db_latency": stage(self.db_latency_ms),
            "tb_latency": stage(self.tb_latency_ms),
            "tb_failures": self.tb_failures,
        }

    def print_summary(self) -> None:
        s = self.summary()
        print(f"processed {s['count']} wafers in {s['elapsed_sec']:.2f}s ({s['throughput_wafers_per_sec']:.1f} wafers/sec)")
        print(f"  end-to-end latency: avg {s['e2e_latency']['avg_ms']:.1f}ms  p99 {s['e2e_latency']['p99_ms']:.1f}ms")
        print(f"  timescaledb insert:  avg {s['db_latency']['avg_ms']:.1f}ms  p99 {s['db_latency']['p99_ms']:.1f}ms")
        print(f"  thingsboard post:    avg {s['tb_latency']['avg_ms']:.1f}ms  p99 {s['tb_latency']['p99_ms']:.1f}ms  ({s['tb_failures']} failed)")


def run(wafers: int) -> None:
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": f"equipment-stream-consumer-{uuid.uuid4().hex[:8]}",
        "auto.offset.reset": "latest",
    })
    consumer.subscribe([TOPIC])
    conn = psycopg.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    stats = Stats()
    print(f"waiting for {wafers} wafers on topic {TOPIC} ...")
    try:
        while stats.count < wafers:
            msg = consumer.poll(timeout=1.0)
            if msg is None or msg.error():
                continue
            consumed_at_ms = int(time.time() * 1000)
            parsed = parse_message(msg.value())
            e2e_ms = latency_ms(parsed["produced_at_ms"], consumed_at_ms)

            db_start = time.monotonic()
            insert_snapshot(conn, parsed["wafer_id"], parsed["defect_class"], parsed["readings"])
            db_ms = (time.monotonic() - db_start) * 1000

            tb_start = time.monotonic()
            tb_ok = telemetry.send_equipment_snapshot(parsed["readings"])
            tb_ms = (time.monotonic() - tb_start) * 1000

            stats.record(e2e_ms, db_ms, tb_ms, tb_ok)
    finally:
        consumer.close()
        conn.close()
    stats.print_summary()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wafers", type=int, default=1000)
    args = parser.parse_args()
    run(args.wafers)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_kafka_consumer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full test suite**

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: all tests pass, including every pre-existing test (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/daol_fascope/kafka_consumer.py tests/test_kafka_consumer.py
git commit -m "feat: add Kafka consumer with TimescaleDB+ThingsBoard dual-write and latency stats"
```

- [ ] **Step 7: End-to-end smoke test (manual, real broker/DB/ThingsBoard)**

Terminal 1:
```bash
cd /home/admin/daol-fascope
docker compose up -d kafka timescaledb thingsboard
THINGSBOARD_DEVICE_TOKEN=<real token> PYTHONPATH=src python -m daol_fascope.kafka_consumer --wafers 200
```
Expected: prints `waiting for 200 wafers on topic equipment-telemetry-stream ...` and blocks.

Terminal 2 (after Terminal 1 is waiting):
```bash
cd /home/admin/daol-fascope
PYTHONPATH=src python -m daol_fascope.kafka_producer --wafers 200
```
Expected: Terminal 2 prints `produced 200 wafers in ...s (...wafers/sec)`. Terminal 1 then prints the 4-line summary block (throughput + e2e/db/thingsboard latency in ms) and exits.

Verify DB side:
```bash
docker exec daol-fascope-timescaledb psql -U wafer_fa -d wafer_fa -c \
  "SELECT count(*) FROM equipment_telemetry WHERE wafer_id LIKE 'STREAM_%';"
```
Expected: `200 * 562 = 112400`.

This step confirms the millisecond-level real-time processing the user asked about — read the printed `end-to-end latency avg/p99` line directly.

---

## Post-plan

Both scripts and the compose service are additive — nothing in Phase 1-3's existing pipeline is touched. If the smoke test numbers look good and the user wants this to become a permanent demo path (not just a one-off measurement), that's a new spec: continuous producer, ThingsBoard perf widget, consumer as a long-running service, etc. — explicitly out of scope here per the design doc's "범위 밖" section.
