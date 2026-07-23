import pandas as pd

from wafer_fa.build_dashboard_data import _attr_key, build_lot_pattern_counts


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
