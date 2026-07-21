from pathlib import Path

import numpy as np
import pandas as pd
from torch.utils.data import Dataset

from wafer_fa.labels import LABEL_TO_IDX
from wafer_fa.render import render_wafer_map


class WaferDataset(Dataset):
    def __init__(self, manifest_csv: str, split: str, processed_dir: str, processor):
        manifest = pd.read_csv(manifest_csv)
        self.rows = manifest[manifest["split"] == split].reset_index(drop=True)
        self.processed_dir = Path(processed_dir)
        self.processor = processor

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows.iloc[idx]
        matrix = np.load(self.processed_dir / row["path"])
        image = render_wafer_map(matrix)
        pixel_values = self.processor(images=image, return_tensors="pt")["pixel_values"][0]
        label_idx = LABEL_TO_IDX[row["label"]]
        return pixel_values, label_idx
