import torch
from daol_fascope.model import DinoV2Classifier


def test_backbone_frozen_head_trainable():
    model = DinoV2Classifier(num_classes=9)
    assert all(not p.requires_grad for p in model.backbone.parameters())
    assert all(p.requires_grad for p in model.head.parameters())


def test_forward_shape():
    model = DinoV2Classifier(num_classes=9)
    x = torch.randn(2, 3, 224, 224)
    logits = model(x)
    assert logits.shape == (2, 9)
