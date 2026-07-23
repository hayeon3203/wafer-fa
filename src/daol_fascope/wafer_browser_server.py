"""Paginated wafer thumbnail API for the ThingsBoard "Wafer Gallery" widget.

The full manifest (~173k wafers across all classes, including "none") is far
too large to push through a single ThingsBoard device attribute -- so instead
of pre-computing everything, this serves pages on demand and the widget's JS
does infinite scroll against it.

Run: python -m daol_fascope.wafer_browser_server
"""
import base64
import io
import json
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from daol_fascope.render import render_wafer_map

PROCESSED_DIR = "data/processed"
MANIFEST = f"{PROCESSED_DIR}/manifest.csv"
THUMB_SIZE = 64
MAX_LIMIT = 200
PORT = 8091


@lru_cache(maxsize=4000)  # ponytail: LRU over on-demand render, not a full pre-render pass over 173k wafers
def render_thumb_b64(path: str) -> str:
    matrix = np.load(f"{PROCESSED_DIR}/{path}")
    img = render_wafer_map(matrix, size=THUMB_SIZE)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def query_page(manifest: pd.DataFrame, offset: int, limit: int, label: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = manifest if not label else manifest[manifest["label"] == label]
    return rows, rows.iloc[offset:offset + limit]


def page_to_items(page: pd.DataFrame) -> list[dict]:
    return [
        {
            "lot_id": r["lot_id"],
            "wafer_index": int(r["wafer_index"]),
            "label": r["label"],
            "image": render_thumb_b64(r["path"]),
        }
        for _, r in page.iterrows()
    ]


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
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/api/wafers":
                self._send_json({"error": "not found"}, 404)
                return
            qs = parse_qs(parsed.query)
            offset = int(qs.get("offset", ["0"])[0])
            limit = min(int(qs.get("limit", ["40"])[0]), MAX_LIMIT)
            label = qs.get("label", [None])[0]

            rows, page = query_page(manifest, offset, limit, label)
            self._send_json({
                "total": len(rows),
                "offset": offset,
                "items": page_to_items(page),
            })

    return Handler


def main():
    manifest = pd.read_csv(MANIFEST)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(manifest))
    print(f"wafer browser API on :{PORT}, {len(manifest)} wafers indexed")
    server.serve_forever()


if __name__ == "__main__":
    main()
