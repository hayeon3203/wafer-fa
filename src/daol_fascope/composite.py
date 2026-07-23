import numpy as np
from PIL import Image

_STOPS = [
    (0.0, (245, 247, 250)),   # background / no defect signal
    (0.5, (255, 170, 60)),    # mid density
    (1.0, (210, 30, 30)),     # high density
]


def _heat_color(density: np.ndarray) -> np.ndarray:
    """Map a [0,1] density array to an (H,W,3) uint8 RGB array via a 3-stop gradient."""
    rgb = np.zeros(density.shape + (3,), dtype=np.float64)
    for (v0, c0), (v1, c1) in zip(_STOPS[:-1], _STOPS[1:]):
        mask = (density >= v0) & (density <= v1)
        t = np.zeros_like(density)
        span = v1 - v0
        t[mask] = (density[mask] - v0) / span
        for ch in range(3):
            rgb[..., ch][mask] = c0[ch] + t[mask] * (c1[ch] - c0[ch])
    return rgb.astype(np.uint8)


def compute_composite(matrices: list[np.ndarray], grid_size: int = 64) -> Image.Image:
    """Average many wafer-map matrices (varying shapes) into one composite heatmap.

    Each matrix uses 0=no die / 1=normal / 2=defect. Every matrix is resized to a
    common grid (nearest-neighbor, keeps the categorical values exact) before
    averaging, so defect density per grid cell = mean defect rate among the dies
    actually present there across samples. Cells with little/no die coverage
    stay near background color (alpha-blended by coverage).
    """
    n = len(matrices)
    defect_sum = np.zeros((grid_size, grid_size))
    footprint_sum = np.zeros((grid_size, grid_size))
    for matrix in matrices:
        resized = np.array(
            Image.fromarray(matrix.astype(np.uint8)).resize(
                (grid_size, grid_size), Image.NEAREST
            )
        )
        defect_sum += resized == 2
        footprint_sum += resized != 0

    density = np.divide(
        defect_sum, footprint_sum, out=np.zeros_like(defect_sum), where=footprint_sum > 0
    )
    coverage = np.clip(footprint_sum / max(n, 1), 0.0, 1.0)

    heat = _heat_color(density).astype(np.float64)
    background = np.array(_STOPS[0][1], dtype=np.float64)
    alpha = coverage[..., None]
    blended = background * (1 - alpha) + heat * alpha
    return Image.fromarray(blended.astype(np.uint8), mode="RGB")
