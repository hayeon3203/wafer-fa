import time

from daol_fascope.kafka_consumer import Stats, build_copy_buffer, latency_ms


def test_latency_ms_computes_difference():
    assert latency_ms(1_000, 1_050) == 50


def test_build_copy_buffer_formats_one_row():
    buf = build_copy_buffer("2026-07-24T00:00:00+00:00", "STREAM_r1_0", "Center", [("feature_0", 1.5)])
    assert buf == "2026-07-24T00:00:00+00:00\tSTREAM_r1_0\tCenter\tfeature_0\tfeature_0\t1.5\n"


def test_build_copy_buffer_formats_multiple_rows():
    buf = build_copy_buffer("t", "w1", "none", [("feature_0", 1.0), ("feature_1", 2.0)])
    assert buf == "t\tw1\tnone\tfeature_0\tfeature_0\t1.0\nt\tw1\tnone\tfeature_1\tfeature_1\t2.0\n"


def test_stats_summary_reports_count_and_avg_latency():
    stats = Stats()
    stats.start = time.monotonic() - 2.0
    for _ in range(10):
        stats.record(e2e_ms=50.0, db_ms=5.0, tb_ms=20.0, tb_ok=True, poll_ms=10.0)
    summary = stats.summary()
    assert summary["count"] == 10
    assert summary["e2e_latency"]["avg_ms"] == 50.0
    assert summary["db_latency"]["avg_ms"] == 5.0
    assert summary["tb_latency"]["avg_ms"] == 20.0
    assert summary["tb_failures"] == 0
    assert summary["throughput_wafers_per_sec"] > 0


def test_stats_counts_thingsboard_failures():
    stats = Stats()
    stats.record(e2e_ms=1.0, db_ms=1.0, tb_ms=1.0, tb_ok=False, poll_ms=1.0)
    stats.record(e2e_ms=1.0, db_ms=1.0, tb_ms=1.0, tb_ok=True, poll_ms=1.0)
    assert stats.summary()["tb_failures"] == 1


def test_stats_summary_reports_poll_latency():
    stats = Stats()
    for _ in range(5):
        stats.record(e2e_ms=1.0, db_ms=1.0, tb_ms=1.0, tb_ok=True, poll_ms=30.0)
    summary = stats.summary()
    assert summary["poll_latency"]["avg_ms"] == 30.0
    assert summary["poll_latency"]["p99_ms"] == 30.0


def test_stats_accumulates_idle_poll_time():
    stats = Stats()
    stats.record_idle(50.0)
    stats.record_idle(75.0)
    assert stats.idle_poll_ms_total == 125.0
    stats.record(e2e_ms=1.0, db_ms=1.0, tb_ms=1.0, tb_ok=True, poll_ms=1.0)
    assert stats.summary()["idle_poll_ms_total"] == 125.0


def test_stats_idle_poll_time_starts_at_zero():
    stats = Stats()
    assert stats.idle_poll_ms_total == 0.0
