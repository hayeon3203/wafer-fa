import numpy as np
import pandas as pd
import pytest

from daol_fascope import equipment_log
from daol_fascope.labels import CLASSES


def _synthetic_secom(n_rows=200, n_features=45, seed=0):
    """A handful of feature blocks plus sparse columns, just enough to
    exercise the missing-value filter and the sampling/shift math."""
    rng = np.random.default_rng(seed)
    blocks = []
    for i in range(9):
        base = rng.normal(loc=i * 10, scale=1.0, size=(n_rows, 1))
        block = base + rng.normal(scale=0.05, size=(n_rows, 5))
        blocks.append(block)
    data = np.hstack(blocks)
    df = pd.DataFrame(data, columns=[f"feature_{i}" for i in range(data.shape[1])])
    df["feature_sparse_a"] = np.where(rng.random(n_rows) < 0.6, np.nan, rng.normal(size=n_rows))
    df["feature_sparse_b"] = np.where(rng.random(n_rows) < 0.9, np.nan, rng.normal(size=n_rows))
    return df


def test_select_candidate_features_drops_mostly_missing_columns():
    df = _synthetic_secom()
    candidates = equipment_log.select_candidate_features(df)
    assert "feature_sparse_b" not in candidates  # 90% missing > threshold
    assert "feature_0" in candidates


def test_assign_features_randomly_covers_every_label_and_every_candidate_exactly_once():
    df = _synthetic_secom()
    candidates = equipment_log.select_candidate_features(df)
    rng = np.random.default_rng(1)
    assignments = equipment_log.assign_features_randomly(df, candidates, rng)

    assert set(assignments) == set(CLASSES)
    all_assigned = [f for info in assignments.values() for f in info["features"]]
    assert sorted(all_assigned) == sorted(candidates)  # partition, no dupes/drops
    for info in assignments.values():
        assert info["mean"].shape == (len(info["features"]),)
        assert info["cov"].shape == (len(info["features"]), len(info["features"]))


def test_assign_features_randomly_is_reproducible_with_same_seeded_rng():
    df = _synthetic_secom()
    candidates = equipment_log.select_candidate_features(df)
    a = equipment_log.assign_features_randomly(df, candidates, np.random.default_rng(42))
    b = equipment_log.assign_features_randomly(df, candidates, np.random.default_rng(42))
    for class_name in CLASSES:
        assert a[class_name]["features"] == b[class_name]["features"]


@pytest.mark.parametrize("defect_class,expected", [
    ("Center", {"Center"}),
    ("Scratch", {"Scratch"}),
    ("Random", set()),
    ("none", set()),
])
def test_shifted_classes_for_single_cause_classes(defect_class, expected):
    assert equipment_log.shifted_classes_for(defect_class) == frozenset(expected)


def test_shifted_classes_for_near_full_shifts_every_real_defect_but_not_random_or_none():
    shifted = equipment_log.shifted_classes_for("Near-full")
    assert "Near-full" in shifted
    assert "Random" not in shifted
    assert "none" not in shifted
    assert shifted == frozenset(c for c in CLASSES if c not in ("Random", "none"))


def test_sample_wafer_readings_shifts_only_the_defect_classs_own_group():
    df = _synthetic_secom()
    candidates = equipment_log.select_candidate_features(df)
    rng = np.random.default_rng(1)
    assignments = equipment_log.assign_features_randomly(df, candidates, rng)

    own_features = set(assignments["Center"]["features"])
    other_class = next(c for c in CLASSES if c != "Center")
    other_features = set(assignments[other_class]["features"])

    n = 500
    shifted_samples = np.array([
        v for _ in range(n)
        for param, v in equipment_log.sample_wafer_readings(assignments, "Center", rng)
        if param in own_features
    ]).reshape(n, -1)
    baseline_samples = np.array([
        v for _ in range(n)
        for param, v in equipment_log.sample_wafer_readings(assignments, "none", rng)
        if param in own_features
    ]).reshape(n, -1)

    expected_shift = equipment_log.SHIFT_STD * np.sqrt(np.diag(assignments["Center"]["cov"]))
    observed_shift = shifted_samples.mean(axis=0) - baseline_samples.mean(axis=0)
    assert np.allclose(observed_shift, expected_shift, atol=0.6)

    # unrelated group stays at baseline for a Center-defect wafer
    other_shifted = np.array([
        v for _ in range(n)
        for param, v in equipment_log.sample_wafer_readings(assignments, "Center", rng)
        if param in other_features
    ]).reshape(n, -1)
    other_baseline_mean = assignments[other_class]["mean"]
    assert np.allclose(other_shifted.mean(axis=0), other_baseline_mean, atol=0.6)


def test_sample_wafer_readings_returns_one_row_per_candidate_feature():
    df = _synthetic_secom()
    candidates = equipment_log.select_candidate_features(df)
    rng = np.random.default_rng(1)
    assignments = equipment_log.assign_features_randomly(df, candidates, rng)

    rows = equipment_log.sample_wafer_readings(assignments, "Scratch", rng)
    assert len(rows) == len(candidates)
    assert {param for param, _ in rows} == set(candidates)
