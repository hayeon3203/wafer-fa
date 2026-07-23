import csv
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas.core.indexes as _indexes
import pandas.core.indexes.base as _indexes_base
import pandas.core.indexes.range as _indexes_range
from sklearn.model_selection import train_test_split

from daol_fascope.labels import LABEL_TO_IDX

RAW_PATH = Path("data/raw/LSWMD.pkl")
OUT_DIR = Path("data/processed")

# LSWMD.pkl was pickled under a pre-1.0 pandas (module layout was pandas.indexes.*,
# now pandas.core.indexes.*), and under Python 2 (needs latin1 decoding).
sys.modules.setdefault("pandas.indexes", _indexes)
sys.modules.setdefault("pandas.indexes.base", _indexes_base)
sys.modules.setdefault("pandas.indexes.range", _indexes_range)


def _load_raw():
    with open(RAW_PATH, "rb") as f:
        return pickle.load(f, encoding="latin1")


def _extract_label(failure_type):
    try:
        val = np.asarray(failure_type).flatten()
        if val.size == 0:
            return None
        name = str(val[0])
        return name if name in LABEL_TO_IDX else None
    except Exception:
        return None


def main():
    df = _load_raw()
    df["label"] = df["failureType"].apply(_extract_label)
    labeled = df[df["label"].notna()].reset_index(drop=True)

    train_df, temp_df = train_test_split(
        labeled, test_size=0.2, stratify=labeled["label"], random_state=42
    )
    val_df, test_df = train_test_split(
        temp_df, test_size=0.5, stratify=temp_df["label"], random_state=42
    )

    manifest_rows = []
    for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        split_dir = OUT_DIR / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        for i, row in split_df.reset_index(drop=True).iterrows():
            matrix = np.asarray(row["waferMap"], dtype=np.uint8)
            out_path = split_dir / f"{i}.npy"
            np.save(out_path, matrix)
            manifest_rows.append({
                "split": split_name,
                "path": str(out_path.relative_to(OUT_DIR)),
                "label": row["label"],
                "lot_id": row["lotName"],
                "wafer_index": int(row["waferIndex"]),
            })

    with open(OUT_DIR / "manifest.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "path", "label", "lot_id", "wafer_index"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"train={len(train_df)} val={len(val_df)} test={len(test_df)}")


if __name__ == "__main__":
    main()
