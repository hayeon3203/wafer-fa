"""Kafka producer for the equipment-telemetry-stream smoke test (see
docs/superpowers/specs/2026-07-24-kafka-streaming-smoketest-design.md).
Publishes one message per synthetic wafer (562-sensor snapshot, reusing
Phase 3.1's SECOM-derived sampler), unthrottled, until --wafers is reached.

Run: PYTHONPATH=src python -m daol_fascope.kafka_producer --wafers 1000

Start the consumer (kafka_consumer.py) BEFORE running this -- the consumer
group resets to "latest", so it only sees messages produced after it
subscribes. On a cold/reset broker, ensure the topic exists before the first
consumer run (this producer auto-creates it, or pre-create with `kafka-topics
--create`), otherwise the consumer will miss all messages and poll forever.
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
