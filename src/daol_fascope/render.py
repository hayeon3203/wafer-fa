import numpy as np
from PIL import Image

COLOR_MAP = {
    0: (255, 255, 255),  # background (no die)
    1: (160, 160, 160),  # normal die
    2: (220, 30, 30),    # defect die
}


def render_wafer_map(matrix: np.ndarray, size: int = 224) -> Image.Image:
    h, w = matrix.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for value, color in COLOR_MAP.items():
        rgb[matrix == value] = color
    img = Image.fromarray(rgb, mode="RGB")
    if img.size != (size, size):
        img = img.resize((size, size), Image.NEAREST)
    return img


def compute_die_yield(matrix: np.ndarray) -> float:
    """Fraction of good (non-defect) dies among all real dies on the wafer.

    Background cells (value 0, no die present) are excluded from the total.
    """
    normal = int(np.count_nonzero(matrix == 1))
    defect = int(np.count_nonzero(matrix == 2))
    total = normal + defect
    return normal / total if total else 0.0
