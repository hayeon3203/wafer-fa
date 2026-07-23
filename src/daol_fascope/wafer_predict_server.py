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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

from daol_fascope.infer import classify_matrix
from daol_fascope.relay import run_relay
from daol_fascope.render import compute_die_yield, render_wafer_map
from daol_fascope.telemetry import send_classification_telemetry, send_pipeline_stage

PROCESSED_DIR = "data/processed"
MANIFEST = f"{PROCESSED_DIR}/manifest.csv"
CHECKPOINT_PATH = "checkpoints/best_model.pt"
PORT = 8092

_lock = threading.Lock()


def pick_random_sample(manifest: pd.DataFrame) -> pd.Series:
    test_rows = manifest[manifest["split"] == "test"].reset_index(drop=True)
    return test_rows.iloc[random.randrange(len(test_rows))]


def run_pipeline(row: pd.Series, checkpoint_path: str = CHECKPOINT_PATH) -> dict:
    current_stage = "classify"
    try:
        send_pipeline_stage(current_stage)
        matrix = np.load(f"{PROCESSED_DIR}/{row['path']}")
        image = render_wafer_map(matrix)
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

        image_buf = io.BytesIO()
        image.save(image_buf, format="PNG")
        wafer_image_b64 = base64.b64encode(image_buf.getvalue()).decode("ascii")

        send_classification_telemetry(
            lot_id=row["lot_id"],
            wafer_index=int(row["wafer_index"]),
            defect_label=predicted,
            confidence=confidence,
            probs=probs,
            die_yield=compute_die_yield(matrix),
            description=relay_result["description"],
            root_cause=relay_result["root_cause"],
            severity=relay_result["severity"],
            recipe=relay_result["recipe"],
            wafer_image_b64=wafer_image_b64,
        )
        send_pipeline_stage("done")
        return {"predicted": predicted, "confidence": confidence, **relay_result}
    except Exception:
        send_pipeline_stage("error", error_node=current_stage)
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
                    row = pick_random_sample(manifest)
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
