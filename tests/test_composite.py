import numpy as np

from daol_fascope.composite import compute_composite


def test_compute_composite_shape_and_mode():
    matrices = [
        np.array([[1, 1], [1, 2]], dtype=np.uint8),
        np.array([[1, 1], [1, 2]], dtype=np.uint8),
    ]
    img = compute_composite(matrices, grid_size=8)
    assert img.size == (8, 8)
    assert img.mode == "RGB"


def test_compute_composite_no_defect_stays_background():
    matrices = [np.ones((4, 4), dtype=np.uint8) for _ in range(3)]
    img = compute_composite(matrices, grid_size=4)
    px = np.array(img)
    assert np.all(px == np.array([245, 247, 250]))


def test_compute_composite_all_defect_is_hot():
    matrices = [np.full((4, 4), 2, dtype=np.uint8) for _ in range(3)]
    img = compute_composite(matrices, grid_size=4)
    px = np.array(img)
    assert np.all(px == np.array([210, 30, 30]))
