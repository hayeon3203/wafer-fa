"""Synthetic SECS/GEM-style equipment telemetry (Plans.md Phase 3.1/3.2).

Spine is the real WM-811K wafer_id (lot_id + wafer_index); SECOM (Kaggle
paresh2047/uci-semcom, mirrored at UCI archive.ics.uci.edu/179) supplies only
per-sensor-group mean/covariance statistics, resampled per wafer via
numpy.random.multivariate_normal -- individual SECOM rows are never reused
as telemetry values.

No equipment/clustering layer: SECOM's 562 candidate sensors are randomly
split into 9 groups (one per WM-811K defect class) -- correlation-based
clustering was tried and dropped (see Plans.md "3.1 재설계"): silhouette
score rises monotonically with cluster count on this data, i.e. there is no
natural cluster count to discover, so a principled-looking clustering step
would have been theater over an arbitrary choice anyway. The random split is
just as arbitrary but doesn't pretend otherwise. The defect_class <-> sensor
correlation itself is not arbitrary -- it's manufactured deliberately by the
SHIFT_STD mean-shift below, applied consistently to every wafer of a class.
"""
import numpy as np
import pandas as pd

from daol_fascope.labels import CLASSES

MISSING_THRESHOLD = 0.5
SHIFT_STD = 2.0
RANDOM_SEED = 42  # fixes which sensors land in which class's group; SECOM stats are static so this is a one-time choice, not a per-run seed.

# Classes with a real (documented) failure mechanism get their own sensor
# group shifted only. Random has no equipment-specific cause (clean-room
# dust) and none is baseline by definition, so neither shifts even though
# each still owns one group under the 1:1 mapping.
_NO_SHIFT_CLASSES = {"Random", "none"}
# Near-full = several mechanisms failing at once: every "real defect" group
# shifts together, Random/none stay baseline.
NEAR_FULL_COSHIFT_CLASSES = frozenset(c for c in CLASSES if c not in _NO_SHIFT_CLASSES)


def load_secom(data_path: str) -> pd.DataFrame:
    """SECOM feature matrix (whitespace-separated, no header). Columns are
    anonymized (feature_0..feature_589) -- SECOM ships no real names."""
    df = pd.read_csv(data_path, sep=r"\s+", header=None)
    df.columns = [f"feature_{i}" for i in range(df.shape[1])]
    return df


def select_candidate_features(df: pd.DataFrame, missing_threshold: float = MISSING_THRESHOLD) -> list[str]:
    missing_rate = df.isna().mean()
    return list(missing_rate[missing_rate <= missing_threshold].index)


def assign_features_randomly(df: pd.DataFrame, candidates: list[str], rng: np.random.Generator) -> dict[str, dict]:
    """Randomly split candidate sensors into len(CLASSES) groups, one per
    defect class (~equal size). No clustering -- see module docstring."""
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    groups = np.array_split(shuffled, len(CLASSES))

    assignments = {}
    for class_name, features in zip(CLASSES, groups):
        features = list(features)
        sub = df[features].fillna(df[features].mean())
        assignments[class_name] = {
            "features": features,
            "mean": sub.mean().to_numpy(),
            "cov": sub.cov().to_numpy(),
        }
    return assignments


def shifted_classes_for(defect_class: str) -> frozenset:
    """Which sensor groups (by class name) show a +SHIFT_STD excursion for a
    wafer of this defect_class. See Plans.md 3.1 root-cause table."""
    if defect_class == "Near-full":
        return NEAR_FULL_COSHIFT_CLASSES | {"Near-full"}
    if defect_class in _NO_SHIFT_CLASSES:
        return frozenset()
    return frozenset({defect_class})


def sample_wafer_readings(assignments: dict[str, dict], defect_class: str, rng: np.random.Generator) -> list[tuple[str, float]]:
    """One synthetic equipment-log snapshot for a single wafer: one
    (param, value) pair per sensor, across all 9 groups."""
    shifted = shifted_classes_for(defect_class)
    rows = []
    for class_name, info in assignments.items():
        mean = info["mean"]
        if class_name in shifted:
            std = np.sqrt(np.clip(np.diag(info["cov"]), 0, None))
            mean = mean + SHIFT_STD * std
        values = rng.multivariate_normal(mean, info["cov"])
        rows.extend(zip(info["features"], (float(v) for v in values)))
    return rows
