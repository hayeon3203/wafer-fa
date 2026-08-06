"""Predict-button API for the ThingsBoard "Wafer Detail" dashboard.

Owns the only warm LLaVA+DINOv2 process for the demo pipeline (random test
sample -> classify -> 4-node relay). app.py no longer runs the relay for
this reason -- running both at once would double-load LLaVA (~14GB) on the
same GPU. See docs/adr/0005-dedicated-warm-prediction-server.md.

Run: python -m daol_fascope.wafer_predict_server
"""
import base64
import io
import json
import random
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

from daol_fascope.infer import classify_matrix
from daol_fascope.relay import run_relay
from daol_fascope.render import compute_die_yield, render_wafer_map
from daol_fascope.telemetry import (
    send_classification_telemetry,
    send_pipeline_stage,
    send_run_error,
    send_run_started,
)

PROCESSED_DIR = "data/processed"
MANIFEST = f"{PROCESSED_DIR}/manifest.csv"
CHECKPOINT_PATH = "checkpoints/best_model.pt"
PORT = 8092

_lock = threading.Lock()
_last_sample_key = None  # (lot_id, wafer_index) of the previous run, so a new
# run doesn't draw the exact same wafer twice in a row when >1 test sample exists.


def pick_random_sample(manifest: pd.DataFrame, last_key: tuple | None = None) -> pd.Series:
    test_rows = manifest[manifest["split"] == "test"].reset_index(drop=True)
    if last_key is not None and len(test_rows) >= 2:
        while True:
            row = test_rows.iloc[random.randrange(len(test_rows))]
            if (row["lot_id"], row["wafer_index"]) != last_key:
                return row
    return test_rows.iloc[random.randrange(len(test_rows))]


def pick_next_sample(manifest: pd.DataFrame) -> pd.Series:
    """Stateful wrapper around pick_random_sample -- tracks the previous pick
    across calls so consecutive runs don't repeat the same wafer."""
    global _last_sample_key
    row = pick_random_sample(manifest, last_key=_last_sample_key)
    _last_sample_key = (row["lot_id"], row["wafer_index"])
    return row


def run_pipeline(row: pd.Series, checkpoint_path: str = CHECKPOINT_PATH) -> dict:
    run_id = uuid.uuid4().hex
    lot_id = row["lot_id"]
    wafer_index = int(row["wafer_index"])
    current_stage = "classify"
    try:
        matrix = np.load(f"{PROCESSED_DIR}/{row['path']}")
        image = render_wafer_map(matrix, size=512)
        die_yield = compute_die_yield(matrix)
        image_buf = io.BytesIO()
        image.save(image_buf, format="PNG")
        wafer_image_b64 = base64.b64encode(image_buf.getvalue()).decode("ascii")

        # Sent before classify starts so this run's wafer identity/image lands on
        # the dashboard even if classify or relay fails below.
        send_run_started(
            run_id=run_id,
            lot_id=lot_id,
            wafer_index=wafer_index,
            wafer_image_b64=wafer_image_b64,
            die_yield=die_yield,
            started_at=time.time(),
        )
        send_pipeline_stage(current_stage)

        probs = classify_matrix(matrix, checkpoint_path)
        predicted = max(probs, key=probs.get)
        confidence = probs[predicted]

        def on_stage(stage):
            nonlocal current_stage
            current_stage = stage
            send_pipeline_stage(stage)

        relay_result = run_relay(
            image, defect_label=predicted, confidence=confidence, on_stage=on_stage
        )

        send_classification_telemetry(
            run_id=run_id,
            lot_id=lot_id,
            wafer_index=wafer_index,
            defect_label=predicted,
            confidence=confidence,
            probs=probs,
            die_yield=die_yield,
            description=relay_result["description"],
            root_cause=relay_result["root_cause"],
            severity=relay_result["severity"],
            recipe=relay_result["recipe"],
            wafer_image_b64=wafer_image_b64,
            completed_at=time.time(),
        )
        send_pipeline_stage("done")
        return {"run_id": run_id, "predicted": predicted, "confidence": confidence, **relay_result}
    except Exception as exc:
        send_pipeline_stage("error", error_node=current_stage)
        send_run_error(
            run_id=run_id,
            lot_id=lot_id,
            wafer_index=wafer_index,
            error_node=current_stage,
            error_message=str(exc),
        )
        raise


def make_handler(manifest: pd.DataFrame):
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
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.end_headers()

        def do_POST(self):
            if self.path != "/api/predict":
                self._send_json({"error": "not found"}, 404)
                return
            if not _lock.acquire(blocking=False):
                self._send_json({"error": "already running"}, 409)
                return

            send_pipeline_stage("idle")
            self._send_json({"status": "accepted"}, 202)

            def _run():
                try:
                    row = pick_next_sample(manifest)
                    run_pipeline(row)
                except Exception as exc:
                    # run_pipeline already reported pipeline_stage=error; this is
                    # just so the failure isn't silently swallowed in server logs.
                    print(f"[wafer_predict_server] pipeline failed: {exc}", flush=True)
                finally:
                    _lock.release()

            threading.Thread(target=_run, daemon=True).start()

    return Handler


def main():
    manifest = pd.read_csv(MANIFEST)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(manifest))
    print(f"wafer_predict_server listening on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
