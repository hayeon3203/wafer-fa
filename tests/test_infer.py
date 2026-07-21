import numpy as np
import torch

from wafer_fa.infer import classify_matrix
from wafer_fa.labels import CLASSES
from wafer_fa.model import DinoV2Classifier


def test_classify_matrix_returns_full_distribution(tmp_path):
    model = DinoV2Classifier(num_classes=len(CLASSES))
    ckpt_path = tmp_path / "model.pt"
    torch.save(
        {"head_state_dict": model.head.state_dict(), "idx_to_label": {i: c for i, c in enumerate(CLASSES)}},
        ckpt_path,
    )
    matrix = np.array([[0, 1, 2], [1, 1, 2], [0, 0, 1]], dtype=np.uint8)
    probs = classify_matrix(matrix, checkpoint_path=str(ckpt_path))
    assert set(probs.keys()) == set(CLASSES)
    assert abs(sum(probs.values()) - 1.0) < 1e-4
