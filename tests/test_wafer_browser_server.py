import numpy as np
import pandas as pd

from wafer_fa.wafer_browser_server import page_to_items, query_page, render_thumb_b64


def _manifest():
    return pd.DataFrame([
        {"lot_id": "lot1", "wafer_index": 0, "label": "Center", "path": "a.npy"},
        {"lot_id": "lot1", "wafer_index": 1, "label": "none", "path": "b.npy"},
        {"lot_id": "lot2", "wafer_index": 0, "label": "none", "path": "c.npy"},
    ])


def test_query_page_paginates():
    manifest = _manifest()
    rows, page = query_page(manifest, offset=1, limit=1, label=None)
    assert len(rows) == 3
    assert page.iloc[0]["lot_id"] == "lot1" and page.iloc[0]["wafer_index"] == 1


def test_query_page_filters_by_label_including_none():
    manifest = _manifest()
    rows, page = query_page(manifest, offset=0, limit=10, label="none")
    assert len(rows) == 2
    assert set(page["lot_id"]) == {"lot1", "lot2"}


def test_page_to_items(tmp_path, monkeypatch):
    monkeypatch.setattr("wafer_fa.wafer_browser_server.PROCESSED_DIR", str(tmp_path))
    render_thumb_b64.cache_clear()
    np.save(tmp_path / "a.npy", np.array([[1, 2], [1, 1]], dtype=np.uint8))
    page = pd.DataFrame([{"lot_id": "lot1", "wafer_index": 0, "label": "Center", "path": "a.npy"}])

    items = page_to_items(page)
    assert len(items) == 1
    assert items[0] == {
        "lot_id": "lot1", "wafer_index": 0, "label": "Center",
        "image": items[0]["image"],
    }
    assert isinstance(items[0]["image"], str) and len(items[0]["image"]) > 0
