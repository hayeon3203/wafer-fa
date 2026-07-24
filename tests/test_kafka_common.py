from daol_fascope.kafka_common import build_message, parse_message


def test_build_and_parse_message_roundtrip():
    readings = [("feature_0", 1.23), ("feature_1", -4.5)]
    raw = build_message("STREAM_run1_0", "Center", readings)
    parsed = parse_message(raw)
    assert parsed["wafer_id"] == "STREAM_run1_0"
    assert parsed["defect_class"] == "Center"
    assert parsed["readings"] == [list(r) for r in readings]
    assert isinstance(parsed["produced_at_ms"], int)


def test_build_message_returns_bytes():
    raw = build_message("w1", "none", [("feature_0", 1.0)])
    assert isinstance(raw, bytes)
