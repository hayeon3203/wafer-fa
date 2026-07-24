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
