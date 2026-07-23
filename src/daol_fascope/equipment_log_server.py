"""Read-only REST API over TimescaleDB `equipment_telemetry` for the
"Wafer Overview"/"Wafer Detail" ThingsBoard correlation widgets (Plans.md
3.2). Kept separate from wafer_predict_server.py (:8092, the warm
LLaVA+DINOv2 process) on purpose -- this is a plain DB-read server, no
reason to share a process with the GPU pipeline.

Run: PYTHONPATH=src python -m daol_fascope.equipment_log_server
"""
import json
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import psycopg

from daol_fascope.build_equipment_log import MANIFEST, build_assignments

PORT = 8093
MAX_SCATTER_SAMPLE_PER_CLASS = 200
RISK_Z_THRESHOLD = 2.0  # same as equipment_log.SHIFT_STD -- one threshold, not two invented numbers

DB_HOST = os.environ.get("WAFER_FA_DB_HOST", "localhost")
DB_PORT = os.environ.get("WAFER_FA_DB_PORT", "5433")
DB_NAME = os.environ.get("WAFER_FA_DB_NAME", "wafer_fa")
DB_USER = os.environ.get("WAFER_FA_DB_USER", "wafer_fa")
DB_PASSWORD = os.environ.get("WAFER_FA_DB_PASSWORD", "wafer_fa")


def db_connect() -> psycopg.Connection:
    return psycopg.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)


def scatter_points(conn: psycopg.Connection, sensor_x: str, sensor_y: str, sample_per_class: int) -> list[dict]:
    """One (x, y) pair per wafer that has both sensors, downsampled to at
    most sample_per_class per defect_class (there's one row per wafer per
    sensor, so the join below yields at most one row per wafer)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.wafer_id, a.defect_class, a.value, b.value "
            "FROM equipment_telemetry a JOIN equipment_telemetry b USING (wafer_id) "
            "WHERE a.param = %s AND b.param = %s",
            (sensor_x, sensor_y),
        )
        rows = cur.fetchall()

    by_class: dict[str, list[tuple]] = {}
    for wafer_id, defect_class, x, y in rows:
        by_class.setdefault(defect_class, []).append((wafer_id, x, y))

    points = []
    for defect_class, class_rows in by_class.items():
        sample = random.sample(class_rows, min(sample_per_class, len(class_rows)))
        points.extend({"wafer_id": w, "defect_class": defect_class, "x": x, "y": y} for w, x, y in sample)
    return points


def wafer_sensor_readings(conn: psycopg.Connection, manifest: pd.DataFrame, assignments: dict, lot_id: str, wafer_index: int) -> dict:
    row = manifest[(manifest["lot_id"] == lot_id) & (manifest["wafer_index"] == wafer_index)]
    if row.empty:
        return {"error": "wafer not found"}
    defect_class = row.iloc[0]["label"]
    wafer_id = f"{lot_id}_{wafer_index}"

    info = assignments[defect_class]
    features = info["features"]
    baseline_std = np.sqrt(np.clip(np.diag(info["cov"]), 0, None))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT param, value FROM equipment_telemetry WHERE wafer_id = %s AND param = ANY(%s)",
            (wafer_id, features),
        )
        values = dict(cur.fetchall())

    sensors = []
    for i, param in enumerate(features):
        if param not in values:
            continue
        value = values[param]
        deviation = (value - info["mean"][i]) / baseline_std[i] if baseline_std[i] > 0 else 0.0
        sensors.append({
            "param": param,
            "value": value,
            "baseline_mean": float(info["mean"][i]),
            "deviation_std": float(deviation),
        })
    sensors.sort(key=lambda s: abs(s["deviation_std"]), reverse=True)
    return {"wafer_id": wafer_id, "defect_class": defect_class, "sensors": sensors}


def make_handler(manifest: pd.DataFrame, assignments: dict, all_sensors: list[str]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # ponytail: quiet by default; remove to debug requests

        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")  # ponytail: dev-only, tighten if exposed beyond the local network
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            if parsed.path == "/api/sensors":
                self._send_json({"sensors": all_sensors})
                return

            if parsed.path == "/api/scatter":
                sensor_x = qs.get("x", [None])[0]
                sensor_y = qs.get("y", [None])[0]
                if sensor_x not in all_sensors or sensor_y not in all_sensors:
                    self._send_json({"error": "unknown sensor"}, 400)
                    return
                sample_per_class = min(int(qs.get("sample_per_class", [MAX_SCATTER_SAMPLE_PER_CLASS])[0]), MAX_SCATTER_SAMPLE_PER_CLASS)
                conn = db_connect()
                try:
                    points = scatter_points(conn, sensor_x, sensor_y, sample_per_class)
                finally:
                    conn.close()
                self._send_json({"x": sensor_x, "y": sensor_y, "points": points})
                return

            if parsed.path == "/api/wafer-sensors":
                lot_id = qs.get("lot_id", [None])[0]
                wafer_index = qs.get("wafer_index", [None])[0]
                if lot_id is None or wafer_index is None:
                    self._send_json({"error": "lot_id and wafer_index required"}, 400)
                    return
                conn = db_connect()
                try:
                    result = wafer_sensor_readings(conn, manifest, assignments, lot_id, int(wafer_index))
                finally:
                    conn.close()
                self._send_json(result, 404 if "error" in result else 200)
                return

            self._send_json({"error": "not found"}, 404)

    return Handler


def main():
    print("loading SECOM + manifest ...")
    assignments = build_assignments()
    all_sensors = sorted(f for info in assignments.values() for f in info["features"])
    manifest = pd.read_csv(MANIFEST)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(manifest, assignments, all_sensors))
    print(f"equipment_log_server on :{PORT}, {len(all_sensors)} sensors, {len(manifest)} wafers indexed")
    server.serve_forever()


if __name__ == "__main__":
    main()
