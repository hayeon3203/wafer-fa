import base64
import io
import json
import os

import numpy as np
import pandas as pd
import requests

from wafer_fa.composite import compute_composite
from wafer_fa.labels import CLASSES
from wafer_fa.render import render_wafer_map

PROCESSED_DIR = "data/processed"
MANIFEST = f"{PROCESSED_DIR}/manifest.csv"
MAX_SAMPLES_PER_CLASS = 3000
SAMPLE_WAFERS_PER_CLASS = 4

THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8082")
THINGSBOARD_DEVICE_TOKEN = os.environ.get("THINGSBOARD_DEVICE_TOKEN", "")


def _attr_key(label: str) -> str:
    return "composite_" + label.replace("-", "_")


def build_composites(manifest: pd.DataFrame) -> dict[str, str]:
    """Per-class composite heatmap, base64-encoded PNG, keyed by ThingsBoard attribute name."""
    attrs = {}
    for label in CLASSES:
        rows = manifest[manifest["label"] == label]
        if len(rows) > MAX_SAMPLES_PER_CLASS:
            rows = rows.sample(MAX_SAMPLES_PER_CLASS, random_state=42)
        matrices = [np.load(f"{PROCESSED_DIR}/{p}") for p in rows["path"]]
        img = compute_composite(matrices)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        attrs[_attr_key(label)] = base64.b64encode(buf.getvalue()).decode("ascii")
    return attrs


def build_lot_pattern_counts(manifest: pd.DataFrame) -> dict:
    counts = manifest.groupby(["lot_id", "label"]).size().unstack(fill_value=0)
    return {lot: row.to_dict() for lot, row in counts.iterrows()}


def build_sample_wafers(manifest: pd.DataFrame) -> list[dict]:
    """A small real-thumbnail gallery (few per class) for the detail dashboard's wafer grid."""
    samples = []
    for label in CLASSES:
        rows = manifest[manifest["label"] == label]
        if len(rows) == 0:
            continue
        picked = rows.sample(min(SAMPLE_WAFERS_PER_CLASS, len(rows)), random_state=42)
        for _, row in picked.iterrows():
            matrix = np.load(f"{PROCESSED_DIR}/{row['path']}")
            img = render_wafer_map(matrix, size=96)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            samples.append({
                "lot_id": row["lot_id"],
                "wafer_index": int(row["wafer_index"]),
                "label": label,
                "image": base64.b64encode(buf.getvalue()).decode("ascii"),
            })
    return samples


def push_attributes(attrs: dict) -> bool:
    if not THINGSBOARD_DEVICE_TOKEN:
        print("THINGSBOARD_DEVICE_TOKEN not set, skipping push")
        return False
    resp = requests.post(
        f"{THINGSBOARD_URL}/api/v1/{THINGSBOARD_DEVICE_TOKEN}/attributes",
        json=attrs,
        timeout=30,
    )
    return resp.ok


def main():
    manifest = pd.read_csv(MANIFEST)
    composite_attrs = build_composites(manifest)
    lot_pattern_counts = build_lot_pattern_counts(manifest)
    sample_wafers = build_sample_wafers(manifest)

    attrs = {
        **composite_attrs,
        "lot_pattern_counts": json.dumps(lot_pattern_counts),
        "sample_wafers": json.dumps(sample_wafers),
    }
    ok = push_attributes(attrs)
    print(f"pushed {len(attrs)} attributes, ok={ok}")


if __name__ == "__main__":
    main()
