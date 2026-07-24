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
