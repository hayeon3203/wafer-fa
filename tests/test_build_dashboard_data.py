import numpy as np
import pandas as pd

from wafer_fa.build_dashboard_data import _attr_key, build_lot_pattern_counts, build_sample_wafers


def test_attr_key_sanitizes_hyphen():
    assert _attr_key("Edge-Loc") == "composite_Edge_Loc"
    assert _attr_key("Center") == "composite_Center"


def test_build_lot_pattern_counts():
    manifest = pd.DataFrame([
        {"lot_id": "lot1", "label": "Center"},
        {"lot_id": "lot1", "label": "Center"},
        {"lot_id": "lot1", "label": "none"},
        {"lot_id": "lot2", "label": "none"},
    ])
    counts = build_lot_pattern_counts(manifest)
    assert counts["lot1"]["Center"] == 2
    assert counts["lot1"]["none"] == 1
    assert counts["lot2"]["none"] == 1
    assert counts["lot2"]["Center"] == 0


def test_build_sample_wafers(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    (processed / "train").mkdir(parents=True)
    np.save(processed / "train" / "0.npy", np.array([[1, 2], [1, 1]], dtype=np.uint8))
    monkeypatch.setattr("wafer_fa.build_dashboard_data.PROCESSED_DIR", str(processed))

    manifest = pd.DataFrame([
        {"lot_id": "lot1", "wafer_index": 1, "label": "Center", "path": "train/0.npy"},
    ])
    samples = build_sample_wafers(manifest)
    assert len(samples) == 1
    assert samples[0]["lot_id"] == "lot1"
    assert samples[0]["wafer_index"] == 1
    assert samples[0]["label"] == "Center"
    assert isinstance(samples[0]["image"], str) and len(samples[0]["image"]) > 0
