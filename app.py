import random
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from daol_fascope.infer import classify_matrix
from daol_fascope.render import render_wafer_map

PROCESSED_DIR = Path("data/processed")
MANIFEST = PROCESSED_DIR / "manifest.csv"

st.set_page_config(
    page_title="Daol FAScope", page_icon="assets/daol_icon.png", layout="centered"
)
st.title("Daol FAScope — Stage 1 (Local Smoke Test)")
# ponytail: Stage 2 (LangGraph relay) moved to wafer_predict_server.py so it
# has the only warm LLaVA process (see docs/adr/0005). This page is local
# Stage 1 (DINOv2) smoke-testing only, no longer the demo surface -- and it
# no longer sends telemetry, since the ThingsBoard Detail dashboard now only
# expects full pipeline runs from wafer_predict_server.

manifest = pd.read_csv(MANIFEST)
test_rows = manifest[manifest["split"] == "test"].reset_index(drop=True)

if st.button("랜덤 샘플 뽑기"):
    row = test_rows.iloc[random.randrange(len(test_rows))]
    matrix = np.load(PROCESSED_DIR / row["path"])
    image = render_wafer_map(matrix)
    probs = classify_matrix(matrix)

    st.image(image, caption=f"실제 정답: {row['label']}", width=300)
    st.bar_chart(probs)

    predicted = max(probs, key=probs.get)
    st.write(f"**예측: {predicted}** ({probs[predicted]*100:.1f}%)")
