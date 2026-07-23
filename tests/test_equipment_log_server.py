from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from daol_fascope import equipment_log_server as srv


def _mock_conn(fetchall_return):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = fetchall_return
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


def test_scatter_points_caps_per_class_and_preserves_pairs():
    rows = [(f"w{i}", "Center", float(i), float(i * 2)) for i in range(300)]
    rows += [(f"n{i}", "none", float(i), float(i * 2)) for i in range(5)]
    conn, cursor = _mock_conn(rows)

    points = srv.scatter_points(conn, "feature_1", "feature_2", sample_per_class=200)

    center_points = [p for p in points if p["defect_class"] == "Center"]
    none_points = [p for p in points if p["defect_class"] == "none"]
    assert len(center_points) == 200  # capped
    assert len(none_points) == 5  # under cap, all kept
    for p in points:
        assert p["y"] == p["x"] * 2  # pairing preserved through the cap/sample


def test_wafer_sensor_readings_computes_deviation_and_sorts_by_magnitude():
    manifest = pd.DataFrame([
        {"lot_id": "lot1", "wafer_index": 0, "label": "Center"},
    ])
    assignments = {
        "Center": {
            "features": ["feature_0", "feature_1"],
            "mean": np.array([10.0, 20.0]),
            "cov": np.array([[4.0, 0.0], [0.0, 1.0]]),  # std = [2, 1]
        },
    }
    conn, cursor = _mock_conn([("feature_0", 14.0), ("feature_1", 20.5)])

    result = srv.wafer_sensor_readings(conn, manifest, assignments, "lot1", 0)

    assert result["defect_class"] == "Center"
    assert result["wafer_id"] == "lot1_0"
    # feature_0: (14-10)/2 = 2.0 std ; feature_1: (20.5-20)/1 = 0.5 std
    assert result["sensors"][0]["param"] == "feature_0"
    assert result["sensors"][0]["deviation_std"] == 2.0
    assert result["sensors"][1]["param"] == "feature_1"
    assert result["sensors"][1]["deviation_std"] == 0.5


def test_wafer_sensor_readings_unknown_wafer_returns_error():
    manifest = pd.DataFrame([{"lot_id": "lot1", "wafer_index": 0, "label": "Center"}])
    conn, cursor = _mock_conn([])

    result = srv.wafer_sensor_readings(conn, manifest, {}, "lot_missing", 99)

    assert result == {"error": "wafer not found"}
