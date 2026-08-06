import numpy as np
import pandas as pd
import pytest

from daol_fascope import wafer_predict_server as server


def _manifest():
    return pd.DataFrame([
        {"lot_id": "lot1", "wafer_index": 0, "label": "Center", "path": "a.npy", "split": "train"},
        {"lot_id": "lot2", "wafer_index": 3, "label": "none", "path": "b.npy", "split": "test"},
    ])


def _multi_test_manifest():
    return pd.DataFrame([
        {"lot_id": "lot1", "wafer_index": 0, "label": "Center", "path": "a.npy", "split": "test"},
        {"lot_id": "lot2", "wafer_index": 1, "label": "none", "path": "b.npy", "split": "test"},
    ])


def _row(tmp_path):
    matrix = np.array([[1, 2], [1, 1]], dtype=np.uint8)
    np.save(tmp_path / "b.npy", matrix)
    return pd.Series({"lot_id": "lot2", "wafer_index": 3, "label": "none", "path": "b.npy"})


def test_pick_random_sample_only_returns_test_split(monkeypatch):
    monkeypatch.setattr(server.random, "randrange", lambda n: 0)
    row = server.pick_random_sample(_manifest())
    assert row["lot_id"] == "lot2" and row["split"] == "test"


def test_pick_random_sample_skips_repeat_when_multiple_test_rows(monkeypatch):
    calls = iter([0, 0, 1])  # first two draws hit the excluded row, third picks the other
    monkeypatch.setattr(server.random, "randrange", lambda n: next(calls))
    row = server.pick_random_sample(_multi_test_manifest(), last_key=("lot1", 0))
    assert (row["lot_id"], row["wafer_index"]) == ("lot2", 1)


def test_pick_next_sample_avoids_consecutive_repeat(monkeypatch):
    monkeypatch.setattr(server, "_last_sample_key", None)
    seq = iter([0, 0, 1])  # 1st pick -> row0; 2nd pick would repeat row0 so it retries to row1
    monkeypatch.setattr(server.random, "randrange", lambda n: next(seq))
    first = server.pick_next_sample(_multi_test_manifest())
    second = server.pick_next_sample(_multi_test_manifest())
    assert (first["lot_id"], first["wafer_index"]) != (second["lot_id"], second["wafer_index"])


def test_run_pipeline_sends_initial_telemetry_before_classify(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    order = []
    monkeypatch.setattr(
        server, "send_run_started",
        lambda **kwargs: order.append(("run_started", kwargs)) or True,
    )
    monkeypatch.setattr(server, "classify_matrix", lambda matrix, checkpoint_path: order.append(("classify", None)) or {"Center": 0.9, "none": 0.1})

    def fake_run_relay(image, defect_label, confidence, on_stage=None):
        for stage in ["describe", "root_cause", "severity", "recipe"]:
            on_stage(stage)
        return {"description": "d", "root_cause": "r", "severity": "s", "recipe": "c"}

    monkeypatch.setattr(server, "run_relay", fake_run_relay)
    monkeypatch.setattr(server, "send_pipeline_stage", lambda stage, error_node=None: None)
    monkeypatch.setattr(server, "send_classification_telemetry", lambda **kwargs: True)

    server.run_pipeline(row)

    assert [name for name, _ in order] == ["run_started", "classify"]
    started_kwargs = order[0][1]
    assert started_kwargs["lot_id"] == "lot2"
    assert started_kwargs["wafer_index"] == 3
    assert isinstance(started_kwargs["wafer_image_b64"], str) and started_kwargs["wafer_image_b64"]
    assert started_kwargs["die_yield"] == pytest.approx(0.75)
    assert "run_id" in started_kwargs and started_kwargs["run_id"]


def test_run_pipeline_pushes_stages_in_order_and_sends_telemetry(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    monkeypatch.setattr(server, "send_run_started", lambda **kwargs: True)
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
    assert payload["run_id"] == result["run_id"]

    assert result["predicted"] == "Center"
    assert result["description"] == "d"


def test_run_pipeline_classify_failure_reports_classify_as_error_node(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    monkeypatch.setattr(server, "send_run_started", lambda **kwargs: True)

    def boom(matrix, checkpoint_path):
        raise ValueError("checkpoint missing")
    monkeypatch.setattr(server, "classify_matrix", boom)

    stage_calls = []
    monkeypatch.setattr(server, "send_pipeline_stage", lambda stage, error_node=None: stage_calls.append((stage, error_node)))

    error_calls = []
    monkeypatch.setattr(server, "send_run_error", lambda **kwargs: error_calls.append(kwargs) or True)

    with pytest.raises(ValueError):
        server.run_pipeline(row)

    assert stage_calls[-1] == ("error", "classify")
    assert len(error_calls) == 1
    assert error_calls[0]["lot_id"] == "lot2"
    assert error_calls[0]["wafer_index"] == 3
    assert error_calls[0]["error_node"] == "classify"
    assert "checkpoint missing" in error_calls[0]["error_message"]


def test_run_pipeline_relay_failure_reports_failing_node_and_keeps_wafer_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    started_calls = []
    monkeypatch.setattr(server, "send_run_started", lambda **kwargs: started_calls.append(kwargs) or True)
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
    error_calls = []
    monkeypatch.setattr(server, "send_run_error", lambda **kwargs: error_calls.append(kwargs) or True)

    with pytest.raises(RuntimeError):
        server.run_pipeline(row)

    assert stage_calls[-1] == ("error", "root_cause")
    assert telemetry_calls == []
    # the wafer identity from send_run_started went out before relay ever ran
    assert len(started_calls) == 1
    assert started_calls[0]["lot_id"] == "lot2" and started_calls[0]["wafer_index"] == 3
    assert len(error_calls) == 1
    assert error_calls[0]["run_id"] == started_calls[0]["run_id"]
    assert error_calls[0]["error_node"] == "root_cause"
    assert "llava down" in error_calls[0]["error_message"]


def test_run_pipeline_different_runs_get_different_run_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROCESSED_DIR", str(tmp_path))
    row = _row(tmp_path)

    monkeypatch.setattr(server, "send_run_started", lambda **kwargs: True)
    monkeypatch.setattr(server, "send_pipeline_stage", lambda stage, error_node=None: None)
    monkeypatch.setattr(server, "send_classification_telemetry", lambda **kwargs: True)
    monkeypatch.setattr(server, "classify_matrix", lambda matrix, checkpoint_path: {"Center": 0.9})
    monkeypatch.setattr(
        server, "run_relay",
        lambda image, defect_label, confidence, on_stage=None: {"description": "d", "root_cause": "r", "severity": "s", "recipe": "c"},
    )

    first = server.run_pipeline(row)
    second = server.run_pipeline(row)
    assert first["run_id"] != second["run_id"]
