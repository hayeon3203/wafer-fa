import numpy as np
from wafer_fa.render import compute_die_yield, render_wafer_map


def test_render_shape_and_mode():
    matrix = np.array([[0, 1, 2], [1, 1, 2], [0, 0, 1]])
    img = render_wafer_map(matrix, size=224)
    assert img.size == (224, 224)
    assert img.mode == "RGB"


def test_render_color_mapping():
    matrix = np.array([[0, 1, 2], [0, 1, 2], [0, 1, 2]])  # square: no resize needed
    img = render_wafer_map(matrix, size=3)
    px = img.load()
    assert px[0, 0] == (255, 255, 255)
    assert px[1, 0] == (160, 160, 160)
    assert px[2, 0] == (220, 30, 30)


def test_compute_die_yield():
    matrix = np.array([[0, 1, 2], [0, 1, 1], [0, 0, 1]])  # 4 normal, 1 defect
    assert compute_die_yield(matrix) == 0.8


def test_compute_die_yield_no_dies():
    matrix = np.zeros((3, 3))
    assert compute_die_yield(matrix) == 0.0
