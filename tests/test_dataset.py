import numpy as np
import pandas as pd
from transformers import AutoImageProcessor

from daol_fascope.dataset import WaferDataset


def test_dataset_getitem(tmp_path):
    processed = tmp_path / "processed"
    (processed / "train").mkdir(parents=True)
    matrix = np.array([[0, 1, 2], [1, 1, 2]], dtype=np.uint8)
    np.save(processed / "train" / "0.npy", matrix)
    pd.DataFrame([{"split": "train", "path": "train/0.npy", "label": "Center"}]).to_csv(
        processed / "manifest.csv", index=False
    )
    processor = AutoImageProcessor.from_pretrained("facebook/dinov2-base")
    ds = WaferDataset(str(processed / "manifest.csv"), split="train",
                       processed_dir=str(processed), processor=processor)
    assert len(ds) == 1
    pixel_values, label_idx = ds[0]
    assert pixel_values.shape[0] == 3
    assert label_idx == 0
