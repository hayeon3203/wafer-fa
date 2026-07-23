"""Offline batch generator for synthetic SECS/GEM-style equipment telemetry
(Plans.md Phase 3.1). One-shot: run, it fills `equipment_telemetry` in
TimescaleDB, done -- see build_dashboard_data.py for the same pattern.

Run: PYTHONPATH=src python -m daol_fascope.build_equipment_log
"""
import io
import os

import numpy as np
import pandas as pd
import psycopg

from daol_fascope.equipment_log import (
    assign_features_randomly,
    load_secom,
    select_candidate_features,
    shifted_classes_for,
    RANDOM_SEED,
    SHIFT_STD,
)

SECOM_DATA_PATH = os.environ.get("SECOM_DATA_PATH", "data/raw/secom/secom.data")
MANIFEST = os.environ.get("MANIFEST_PATH", "data/processed/manifest.csv")

DB_HOST = os.environ.get("WAFER_FA_DB_HOST", "localhost")
DB_PORT = os.environ.get("WAFER_FA_DB_PORT", "5433")
DB_NAME = os.environ.get("WAFER_FA_DB_NAME", "wafer_fa")
DB_USER = os.environ.get("WAFER_FA_DB_USER", "wafer_fa")
DB_PASSWORD = os.environ.get("WAFER_FA_DB_PASSWORD", "wafer_fa")


def build_assignments(secom_data_path: str = SECOM_DATA_PATH) -> dict[str, dict]:
    df = load_secom(secom_data_path)
    candidates = select_candidate_features(df)
    return assign_features_randomly(df, candidates, np.random.default_rng(RANDOM_SEED))


def load_manifest_with_wafer_id(manifest_path: str = MANIFEST) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_path)
    manifest = manifest.sort_values(["lot_id", "wafer_index"]).reset_index(drop=True)
    manifest["wafer_id"] = manifest["lot_id"] + "_" + manifest["wafer_index"].astype(str)
    return manifest


def build_time_column(manifest: pd.DataFrame) -> pd.Series:
    """Even spread across the last 30 days; row order (lot_id/wafer_index
    sort) stands in for real process order since manifest has no timestamp."""
    now = pd.Timestamp.now(tz="UTC")
    start = now - pd.Timedelta(days=30)
    n = len(manifest)
    fractions = np.arange(n) / max(n - 1, 1)
    return pd.Series(start + (now - start) * fractions, index=manifest.index)


def generate_class_chunk(group: pd.DataFrame, defect_class: str, assignments: dict[str, dict], rng: np.random.Generator) -> pd.DataFrame:
    """All equipment_telemetry rows for one defect_class's wafers, across all 9 equipment."""
    shifted = shifted_classes_for(defect_class)
    n = len(group)
    wafer_id = group["wafer_id"].to_numpy()
    time = group["time"].to_numpy()

    parts = []
    for class_name, info in assignments.items():
        mean = info["mean"]
        if class_name in shifted:
            std = np.sqrt(np.clip(np.diag(info["cov"]), 0, None))
            mean = mean + SHIFT_STD * std
        k = len(info["features"])
        values = rng.multivariate_normal(mean, info["cov"], size=n)  # (n, k)
        features = np.tile(info["features"], n)
        parts.append(pd.DataFrame({
            "time": np.repeat(time, k),
            "wafer_id": np.repeat(wafer_id, k),
            "defect_class": defect_class,
            "equipment_id": features,  # no equipment layer -- see equipment_log.py module docstring
            "param": features,
            "value": values.reshape(-1),
        }))
    return pd.concat(parts, ignore_index=True)


def insert_chunk(conn: psycopg.Connection, chunk: pd.DataFrame) -> None:
    """Bulk COPY via one text blob instead of row-by-row write_row -- needed
    at this scale (~9700만행 total across all chunks, see Plans.md 3.1 재설계)."""
    buf = io.StringIO()
    chunk.to_csv(buf, sep="\t", header=False, index=False)
    buf.seek(0)
    with conn.cursor().copy(
        "COPY equipment_telemetry (time, wafer_id, defect_class, equipment_id, param, value) FROM STDIN"
    ) as copy:
        copy.write(buf.read())


def main():
    print(f"loading SECOM from {SECOM_DATA_PATH} ...")
    assignments = build_assignments()
    for class_name, info in assignments.items():
        print(f"  {class_name:10s} -> {len(info['features'])} sensors")

    manifest = load_manifest_with_wafer_id()
    manifest["time"] = build_time_column(manifest)
    print(f"manifest: {len(manifest)} wafers")

    rng = np.random.default_rng(RANDOM_SEED)
    conn = psycopg.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        total = 0
        for defect_class, group in manifest.groupby("label"):
            chunk = generate_class_chunk(group, defect_class, assignments, rng)
            insert_chunk(conn, chunk)
            conn.commit()
            total += len(chunk)
            print(f"  inserted {len(chunk)} rows for {defect_class} (running total {total})")
        print(f"done, {total} rows in equipment_telemetry")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
