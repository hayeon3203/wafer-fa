import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoImageProcessor

from daol_fascope.labels import CLASSES
from daol_fascope.model import DinoV2Classifier
from daol_fascope.render import render_wafer_map

_processor = None


def _load(checkpoint_path: str):
    global _processor
    if _processor is None:
        _processor = AutoImageProcessor.from_pretrained("facebook/dinov2-base")
    model = DinoV2Classifier(num_classes=len(CLASSES))
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.head.load_state_dict(checkpoint["head_state_dict"])
    model.eval()
    return model, _processor


def classify_matrix(matrix: np.ndarray, checkpoint_path: str = "checkpoints/best_model.pt") -> dict:
    model, processor = _load(checkpoint_path)
    image = render_wafer_map(matrix)
    pixel_values = processor(images=image, return_tensors="pt")["pixel_values"]
    with torch.no_grad():
        logits = model(pixel_values)
        probs = F.softmax(logits, dim=1)[0]
    return {label: probs[i].item() for i, label in enumerate(CLASSES)}
