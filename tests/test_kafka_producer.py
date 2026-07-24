import numpy as np

from daol_fascope.kafka_producer import pick_defect_class


def test_pick_defect_class_returns_value_from_labels():
    rng = np.random.default_rng(0)
    labels = np.array(["Center", "none", "Scratch"])
    result = pick_defect_class(labels, rng)
    assert result in labels


def test_pick_defect_class_is_deterministic_for_seeded_rng():
    labels = np.array(["Center", "none", "Scratch", "Donut"])
    first = pick_defect_class(labels, np.random.default_rng(42))
    second = pick_defect_class(labels, np.random.default_rng(42))
    assert first == second
