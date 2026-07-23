from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from daol_fascope import build_equipment_log as bel


def _fake_assignments():
    rng = np.random.default_rng(0)
    assignments = {}
    for i, name in enumerate(["Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc", "Random", "Scratch", "Near-full", "none"]):
        features = [f"feature_{i}_{j}" for j in range(3)]
        mean = rng.normal(size=3)
        a = rng.normal(size=(3, 3))
        cov = a @ a.T + np.eye(3)  # positive semi-definite
        assignments[name] = {"features": features, "mean": mean, "cov": cov}
    return assignments


def test_load_manifest_with_wafer_id_builds_lot_underscore_index(tmp_path):
    manifest_path = tmp_path / "manifest.csv"
    pd.DataFrame({
        "split": ["train", "train"],
        "path": ["train/0.npy", "train/1.npy"],
        "label": ["none", "Center"],
        "lot_id": ["lot2", "lot1"],
        "wafer_index": [3, 5],
    }).to_csv(manifest_path, index=False)

    manifest = bel.load_manifest_with_wafer_id(str(manifest_path))
    assert list(manifest["wafer_id"]) == ["lot1_5", "lot2_3"]  # sorted by lot_id first


def test_build_time_column_spans_last_30_days_in_order():
    manifest = pd.DataFrame({"lot_id": ["a"] * 5, "wafer_index": range(5)})
    times = bel.build_time_column(manifest)
    assert times.is_monotonic_increasing
    span = times.iloc[-1] - times.iloc[0]
    assert span <= pd.Timedelta(days=30)
    assert (pd.Timestamp.now(tz="UTC") - times.iloc[-1]) < pd.Timedelta(minutes=1)


def test_generate_class_chunk_shifted_class_has_higher_mean_than_baseline():
    assignments = _fake_assignments()
    rng = np.random.default_rng(1)
    group = pd.DataFrame({
        "wafer_id": [f"lot1_{i}" for i in range(2000)],
        "time": pd.Timestamp.now(tz="UTC"),
    })

    center_chunk = bel.generate_class_chunk(group, "Center", assignments, rng)
    none_chunk = bel.generate_class_chunk(group, "none", assignments, rng)

    center_own_feature = assignments["Center"]["features"][0]
    donut_feature = assignments["Donut"]["features"][0]

    center_own = center_chunk[center_chunk["param"] == center_own_feature]["value"]
    none_own = none_chunk[none_chunk["param"] == center_own_feature]["value"]
    assert center_own.mean() > none_own.mean() + 1.0  # Center owns this sensor group, shifted by +2*std

    # unrelated group (owned by Donut) stays near baseline for Center wafers
    center_other = center_chunk[center_chunk["param"] == donut_feature]["value"]
    none_other = none_chunk[none_chunk["param"] == donut_feature]["value"]
    assert abs(center_other.mean() - none_other.mean()) < 1.0


def test_generate_class_chunk_row_count_and_columns():
    assignments = _fake_assignments()
    rng = np.random.default_rng(2)
    group = pd.DataFrame({"wafer_id": ["lot1_1", "lot1_2"], "time": pd.Timestamp.now(tz="UTC")})

    chunk = bel.generate_class_chunk(group, "Scratch", assignments, rng)
    expected_rows = len(group) * sum(len(info["features"]) for info in assignments.values())
    assert len(chunk) == expected_rows
    assert set(chunk.columns) == {"time", "wafer_id", "defect_class", "equipment_id", "param", "value"}
    assert (chunk["defect_class"] == "Scratch").all()
    assert (chunk["equipment_id"] == chunk["param"]).all()  # no equipment layer -- equipment_id mirrors param
    all_features = {f for info in assignments.values() for f in info["features"]}
    assert set(chunk["param"]) == all_features


def test_insert_chunk_writes_one_tsv_blob_with_all_rows():
    chunk = pd.DataFrame({
        "time": [pd.Timestamp.now(tz="UTC")] * 3,
        "wafer_id": ["lot1_1"] * 3,
        "defect_class": ["Center"] * 3,
        "equipment_id": ["feature_0", "feature_1", "feature_2"],
        "param": ["feature_0", "feature_1", "feature_2"],
        "value": [1.0, 2.0, 3.0],
    })
    mock_copy = MagicMock()
    mock_copy.__enter__ = MagicMock(return_value=mock_copy)
    mock_copy.__exit__ = MagicMock(return_value=False)
    mock_cursor = MagicMock()
    mock_cursor.copy.return_value = mock_copy
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    bel.insert_chunk(mock_conn, chunk)

    mock_copy.write.assert_called_once()
    written = mock_copy.write.call_args[0][0]
    assert written.count("\n") == 3  # 3 data rows, trailing newline from to_csv
    assert "feature_1" in written
    mock_cursor.copy.assert_called_once()
    assert "equipment_telemetry" in mock_cursor.copy.call_args[0][0]
