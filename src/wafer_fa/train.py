import os

import numpy as np
import torch
from sklearn.metrics import classification_report, f1_score
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader
from transformers import AutoImageProcessor

from wafer_fa.dataset import WaferDataset
from wafer_fa.labels import CLASSES, LABEL_TO_IDX
from wafer_fa.model import DinoV2Classifier

MANIFEST = "data/processed/manifest.csv"
PROCESSED_DIR = "data/processed"
TARGET_MACRO_F1 = 0.80


def run_epoch(model, loader, optimizer, criterion, device, train=True):
    model.train() if train else model.eval()
    all_preds, all_labels = [], []
    total_loss = 0.0
    for pixel_values, labels in loader:
        pixel_values, labels = pixel_values.to(device), labels.to(device)
        with torch.set_grad_enabled(train):
            logits = model(pixel_values)
            loss = criterion(logits, labels)
            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        total_loss += loss.item() * len(labels)
        all_preds.extend(logits.argmax(dim=1).cpu().tolist())
        all_labels.extend(labels.cpu().tolist())
    macro_f1 = f1_score(all_labels, all_preds, average="macro")
    return total_loss / len(loader.dataset), macro_f1, all_preds, all_labels


def main(epochs: int = 10, batch_size: int = 32, lr: float = 1e-3):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained("facebook/dinov2-base")

    train_ds = WaferDataset(MANIFEST, "train", PROCESSED_DIR, processor)
    val_ds = WaferDataset(MANIFEST, "val", PROCESSED_DIR, processor)
    test_ds = WaferDataset(MANIFEST, "test", PROCESSED_DIR, processor)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size)
    test_loader = DataLoader(test_ds, batch_size=batch_size)

    train_labels = train_ds.rows["label"].map(LABEL_TO_IDX).to_numpy()
    class_weights = compute_class_weight(
        "balanced", classes=np.arange(len(CLASSES)), y=train_labels
    )
    weight_tensor = torch.tensor(class_weights, dtype=torch.float32, device=device)
    criterion = torch.nn.CrossEntropyLoss(weight=weight_tensor)

    model = DinoV2Classifier(num_classes=len(CLASSES)).to(device)
    optimizer = torch.optim.Adam(model.head.parameters(), lr=lr)

    os.makedirs("checkpoints", exist_ok=True)
    best_val_f1 = 0.0
    for epoch in range(epochs):
        train_loss, train_f1, _, _ = run_epoch(model, train_loader, optimizer, criterion, device, train=True)
        val_loss, val_f1, _, _ = run_epoch(model, val_loader, optimizer, criterion, device, train=False)
        print(f"epoch {epoch}: train_loss={train_loss:.4f} train_f1={train_f1:.3f} val_loss={val_loss:.4f} val_f1={val_f1:.3f}")
        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            torch.save(
                {"head_state_dict": model.head.state_dict(), "idx_to_label": {i: c for i, c in enumerate(CLASSES)}},
                "checkpoints/best_model.pt",
            )

    checkpoint = torch.load("checkpoints/best_model.pt")
    model.head.load_state_dict(checkpoint["head_state_dict"])
    _, test_f1, test_preds, test_labels = run_epoch(model, test_loader, optimizer, criterion, device, train=False)
    print(classification_report(test_labels, test_preds, target_names=CLASSES))
    print(f"TEST macro F1 = {test_f1:.3f} (target >= {TARGET_MACRO_F1}) -> {'PASS' if test_f1 >= TARGET_MACRO_F1 else 'FAIL'}")


if __name__ == "__main__":
    main()
