import base64
import io
import random
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from wafer_fa.infer import classify_matrix
from wafer_fa.relay import run_relay
from wafer_fa.render import compute_die_yield, render_wafer_map
from wafer_fa.telemetry import send_classification_telemetry

PROCESSED_DIR = Path("data/processed")
MANIFEST = PROCESSED_DIR / "manifest.csv"

st.set_page_config(
    page_title="Wafer Defect Classifier", page_icon="assets/daol_icon.png", layout="centered"
)
# ponytail: hides Streamlit's default top-right "running" indicator (animated
# running-person icon + stop button) since st.spinner below already shows
# progress; relay runs take minutes so that indicator stays visible the whole
# time otherwise. Cosmetic only, no effect on actual execution.
st.markdown(
    "<style>[data-testid='stStatusWidget'] { visibility: hidden; }</style>",
    unsafe_allow_html=True,
)
st.title("Wafer Defect Classifier — Stage 1 + 2")

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

    with st.spinner("에이전트 릴레이 실행 중 (설명 → 원인분석 → 심각도 → 해결책)..."):
        relay_result = run_relay(image, defect_label=predicted, confidence=probs[predicted])

    st.subheader("결함 설명")
    st.write(relay_result["description"])
    st.subheader("원인 분석")
    st.write(relay_result["root_cause"])
    st.subheader("심각도")
    st.write(relay_result["severity"])
    st.subheader("해결책 제안")
    st.write(relay_result["recipe"])

    image_buf = io.BytesIO()
    image.save(image_buf, format="PNG")
    wafer_image_b64 = base64.b64encode(image_buf.getvalue()).decode("ascii")

    send_classification_telemetry(
        lot_id=row["lot_id"],
        wafer_index=int(row["wafer_index"]),
        defect_label=predicted,
        confidence=probs[predicted],
        probs=probs,
        die_yield=compute_die_yield(matrix),
        description=relay_result["description"],
        root_cause=relay_result["root_cause"],
        severity=relay_result["severity"],
        recipe=relay_result["recipe"],
        wafer_image_b64=wafer_image_b64,
    )
