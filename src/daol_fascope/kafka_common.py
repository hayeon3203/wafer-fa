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
