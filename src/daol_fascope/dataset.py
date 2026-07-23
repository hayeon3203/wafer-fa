import random
from pathlib import Path

import numpy as np
import pandas as pd
from torch.utils.data import Dataset

from daol_fascope.labels import LABEL_TO_IDX
from daol_fascope.render import render_wafer_map


def _random_dihedral(matrix: np.ndarray) -> np.ndarray:
    """Apply a random rotation/flip from the wafer's 8-fold dihedral symmetry.

    A wafer has no fixed physical orientation, so any rotation or mirror of
    its die grid is an equally valid sample of the same defect pattern.
    """
    k = random.randint(0, 3)
    matrix = np.rot90(matrix, k)
    if random.random() < 0.5:
        matrix = np.fliplr(matrix)
    return matrix


class WaferDataset(Dataset):
    def __init__(self, manifest_csv: str, split: str, processed_dir: str, processor, augment: bool | None = None):
        manifest = pd.read_csv(manifest_csv)
        self.rows = manifest[manifest["split"] == split].reset_index(drop=True)
        self.processed_dir = Path(processed_dir)
        self.processor = processor
        self.augment = (split == "train") if augment is None else augment

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows.iloc[idx]
        matrix = np.load(self.processed_dir / row["path"])
        if self.augment:
            matrix = _random_dihedral(matrix)
        image = render_wafer_map(matrix)
        pixel_values = self.processor(images=image, return_tensors="pt")["pixel_values"][0]
        label_idx = LABEL_TO_IDX[row["label"]]
        return pixel_values, label_idx
