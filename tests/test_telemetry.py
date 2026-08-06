from unittest.mock import patch

import requests

from daol_fascope import telemetry


def test_send_classification_telemetry_no_token_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "")
    assert telemetry.send_classification_telemetry(
        lot_id="lot1", wafer_index=1, defect_label="Center",
        confidence=0.9, probs={"Center": 0.9, "none": 0.1},
    ) is False


def test_send_classification_telemetry_posts_payload(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    monkeypatch.setattr(telemetry, "THINGSBOARD_URL", "http://tb.local")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        result = telemetry.send_classification_telemetry(
            lot_id="lot1", wafer_index=1, defect_label="Center",
            confidence=0.9, probs={"Center": 0.9, "none": 0.1}, severity="MAJOR",
        )
    assert result is True
    url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert url == "http://tb.local/api/v1/tok123/telemetry"
    assert kwargs["json"]["lot_id"] == "lot1"
    assert kwargs["json"]["severity"] == "MAJOR"
    assert kwargs["json"]["prob_Center"] == 0.9


def test_send_classification_telemetry_includes_relay_fields(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        telemetry.send_classification_telemetry(
            lot_id="lot1", wafer_index=1, defect_label="Center",
            confidence=0.9, probs={"Center": 0.9},
            die_yield=0.8, description="설명", root_cause="원인",
            severity="MAJOR", recipe="해결책", wafer_image_b64="base64data",
        )
    payload = mock_post.call_args[1]["json"]
    assert payload["die_yield"] == 0.8
    assert payload["die_yield_pct"] == 80.0
    assert payload["description"] == "설명"
    assert payload["root_cause"] == "원인"
    assert payload["recipe"] == "해결책"
    assert payload["wafer_image"] == "base64data"


def test_send_classification_telemetry_network_error_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post", side_effect=requests.RequestException("boom")):
        result = telemetry.send_classification_telemetry(
            lot_id="lot1", wafer_index=1, defect_label="Center",
            confidence=0.9, probs={"Center": 0.9},
        )
    assert result is False


def test_send_pipeline_stage_no_token_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "")
    assert telemetry.send_pipeline_stage("classify") is False


def test_send_pipeline_stage_posts_payload(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    monkeypatch.setattr(telemetry, "THINGSBOARD_URL", "http://tb.local")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        result = telemetry.send_pipeline_stage("describe")
    assert result is True
    url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert url == "http://tb.local/api/v1/tok123/telemetry"
    assert kwargs["json"] == {"pipeline_stage": "describe"}


def test_send_pipeline_stage_error_includes_error_node(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        telemetry.send_pipeline_stage("error", error_node="root_cause")
    payload = mock_post.call_args[1]["json"]
    assert payload == {"pipeline_stage": "error", "pipeline_stage_error_node": "root_cause"}


def test_send_pipeline_stage_network_error_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post", side_effect=requests.RequestException("boom")):
        assert telemetry.send_pipeline_stage("classify") is False


def test_send_equipment_snapshot_posts_one_payload_per_wafer(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    monkeypatch.setattr(telemetry, "THINGSBOARD_URL", "http://tb.local")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        result = telemetry.send_equipment_snapshot([("feature_0", 1.5), ("feature_1", -2.0)])
    assert result is True
    assert mock_post.call_count == 1
    url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
    assert url == "http://tb.local/api/v1/tok123/telemetry"
    assert kwargs["json"] == {"feature_0": 1.5, "feature_1": -2.0}


def test_send_equipment_snapshot_no_token_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "")
    assert telemetry.send_equipment_snapshot([("feature_0", 1.0)]) is False


def test_send_run_started_posts_identity_before_analysis_with_running_status(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    monkeypatch.setattr(telemetry, "THINGSBOARD_URL", "http://tb.local")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        result = telemetry.send_run_started(
            run_id="run-1", lot_id="lot1", wafer_index=1,
            wafer_image_b64="base64data", die_yield=0.5, started_at=100.0,
        )
    assert result is True
    payload = mock_post.call_args[1]["json"]
    assert payload["run_id"] == "run-1"
    assert payload["lot_id"] == "lot1"
    assert payload["wafer_index"] == 1
    assert payload["wafer_image"] == "base64data"
    assert payload["die_yield"] == 0.5
    assert payload["die_yield_pct"] == 50.0
    assert payload["pipeline_stage"] == "classify"
    assert payload["result_status"] == "running"
    assert payload["started_at"] == 100.0


def test_send_run_error_posts_error_status_with_same_run_id(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        telemetry.send_run_error(
            run_id="run-1", lot_id="lot1", wafer_index=1,
            error_node="root_cause", error_message="llava down",
        )
    payload = mock_post.call_args[1]["json"]
    assert payload == {
        "run_id": "run-1",
        "lot_id": "lot1",
        "wafer_index": 1,
        "pipeline_stage": "error",
        "pipeline_stage_error_node": "root_cause",
        "result_status": "error",
        "error_message": "llava down",
    }


def test_send_classification_telemetry_includes_run_id_and_done_status(monkeypatch):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = True
        telemetry.send_classification_telemetry(
            run_id="run-1", lot_id="lot1", wafer_index=1, defect_label="Center",
            confidence=0.9, probs={"Center": 0.9}, completed_at=200.0,
        )
    payload = mock_post.call_args[1]["json"]
    assert payload["run_id"] == "run-1"
    assert payload["pipeline_stage"] == "done"
    assert payload["result_status"] == "done"
    assert payload["completed_at"] == 200.0


def test_post_failure_logs_status_and_body(monkeypatch, capsys):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post") as mock_post:
        mock_post.return_value.ok = False
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "internal error"
        result = telemetry._post({"pipeline_stage": "done"})
    assert result is False
    err = capsys.readouterr().out
    assert "[telemetry]" in err and "500" in err and "internal error" in err


def test_post_network_error_logs(monkeypatch, capsys):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "tok123")
    with patch.object(telemetry.requests, "post", side_effect=requests.RequestException("boom")):
        result = telemetry._post({"pipeline_stage": "done"})
    assert result is False
    out = capsys.readouterr().out
    assert "[telemetry]" in out and "boom" in out


def test_post_no_token_logs(monkeypatch, capsys):
    monkeypatch.setattr(telemetry, "THINGSBOARD_DEVICE_TOKEN", "")
    result = telemetry._post({"pipeline_stage": "done"})
    assert result is False
    out = capsys.readouterr().out
    assert "[telemetry]" in out and "THINGSBOARD_DEVICE_TOKEN" in out
