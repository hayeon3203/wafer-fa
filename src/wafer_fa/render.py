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
        img = img.resize((size, size), Image.BILINEAR)
    return img
