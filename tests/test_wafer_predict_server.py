import numpy as np
import pandas as pd
import pytest

from daol_fascope import wafer_predict_server as server


def _manifest():
    return pd.DataFrame([
        {"lot_id": "lot1", "wafer_index": 0, "label": "Center", "path": "a.npy", "split": "train"},
        {"lot_id": "lot2", "wafer_index": 3, "label": "none", "path": "b.npy", "split": "test"},
    ])


def _row(tmp_path):
    matrix = np.array([[1, 2], [1, 1]], dtype=np.uint8)
    np.save(tmp_path / "b.npy", matrix)
    return pd.Series({"lot_id": "lot2", "wafer_index": 3, "label": "none", "path": "b.npy"})


def test_pick_random_sample_only_returns_test_split(monkeypatch):
    monkeypatch.setattr(server.random, "randrange", lambda n: 0)
    row = server.pick_random_sample(_manifest())
    assert row["lot_id"] == "lot2" and row["split"] == "test"


def test_run_pipeline_pushes_stages_in_order_and_sends_telemetry(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    monkeypatch.setattr(server, "classify_matrix", lambda matrix, checkpoint_path: {"Center": 0.9, "none": 0.1})

    def fake_run_relay(image, defect_label, confidence, on_stage=None):
        for stage in ["describe", "root_cause", "severity", "recipe"]:
            on_stage(stage)
        return {"description": "d", "root_cause": "r", "severity": "s", "recipe": "c"}

    monkeypatch.setattr(server, "run_relay", fake_run_relay)

    stage_calls = []
    monkeypatch.setattr(server, "send_pipeline_stage", lambda stage, error_node=None: stage_calls.append((stage, error_node)))

    telemetry_calls = []
    monkeypatch.setattr(
        server, "send_classification_telemetry",
        lambda **kwargs: telemetry_calls.append(kwargs) or True,
    )

    result = server.run_pipeline(row)

    assert stage_calls == [
        ("classify", None), ("describe", None), ("root_cause", None),
        ("severity", None), ("recipe", None), ("done", None),
    ]
    assert len(telemetry_calls) == 1
    payload = telemetry_calls[0]
    assert payload["lot_id"] == "lot2"
    assert payload["wafer_index"] == 3
    assert payload["defect_label"] == "Center"
    assert payload["confidence"] == 0.9
    assert payload["description"] == "d" and payload["recipe"] == "c"
    assert isinstance(payload["wafer_image_b64"], str) and len(payload["wafer_image_b64"]) > 0

    assert result["predicted"] == "Center"
    assert result["description"] == "d"


def test_run_pipeline_classify_failure_reports_classify_as_error_node(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    def boom(matrix, checkpoint_path):
        raise ValueError("checkpoint missing")
    monkeypatch.setattr(server, "classify_matrix", boom)

    stage_calls = []
    monkeypatch.setattr(server, "send_pipeline_stage", lambda stage, error_node=None: stage_calls.append((stage, error_node)))

    with pytest.raises(ValueError):
        server.run_pipeline(row)

    assert stage_calls[-1] == ("error", "classify")


def test_run_pipeline_relay_failure_reports_failing_node(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)
    monkeypatch.setattr(server, "classify_matrix", lambda matrix, checkpoint_path: {"Center": 0.9})

    def fake_run_relay(image, defect_label, confidence, on_stage=None):
        on_stage("describe")
        on_stage("root_cause")
        raise RuntimeError("llava down")
    monkeypatch.setattr(server, "run_relay", fake_run_relay)

    stage_calls = []
    monkeypatch.setattr(server, "send_pipeline_stage", lambda stage, error_node=None: stage_calls.append((stage, error_node)))
    telemetry_calls = []
    monkeypatch.setattr(server, "send_classification_telemetry", lambda **kwargs: telemetry_calls.append(kwargs))

    with pytest.raises(RuntimeError):
        server.run_pipeline(row)

    assert stage_calls[-1] == ("error", "root_cause")
    assert telemetry_calls == []
