import torch.nn as nn
from transformers import AutoModel


class DinoV2Classifier(nn.Module):
    def __init__(self, num_classes: int = 9, backbone_name: str = "facebook/dinov2-base"):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(backbone_name)
        for p in self.backbone.parameters():
            p.requires_grad = False
        hidden_size = self.backbone.config.hidden_size
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 256),
            nn.ReLU(),
            nn.Linear(256, num_classes),
        )

    def forward(self, pixel_values):
        self.backbone.eval()
        out = self.backbone(pixel_values=pixel_values)
        cls_token = out.last_hidden_state[:, 0, :]
        return self.head(cls_token)
