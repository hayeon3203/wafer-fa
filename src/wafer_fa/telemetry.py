import os

import requests

THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8082")
THINGSBOARD_DEVICE_TOKEN = os.environ.get("THINGSBOARD_DEVICE_TOKEN", "")


def send_classification_telemetry(
    *, lot_id, wafer_index, defect_label, confidence, probs, severity=None
) -> bool:
    """POST one classification result to the ThingsBoard demo dashboard device.

    Optional integration: returns False (never raises) if THINGSBOARD_DEVICE_TOKEN
    isn't set or the request fails, so the classifier demo works with ThingsBoard down.
    """
    if not THINGSBOARD_DEVICE_TOKEN:
        return False
    payload = {
        "lot_id": lot_id,
        "wafer_index": wafer_index,
        "defect_class": defect_label,
        "confidence": confidence,
        **{f"prob_{k}": v for k, v in probs.items()},
    }
    if severity is not None:
        payload["severity"] = severity
    try:
        resp = requests.post(
            f"{THINGSBOARD_URL}/api/v1/{THINGSBOARD_DEVICE_TOKEN}/telemetry",
            json=payload,
            timeout=5,
        )
        return resp.ok
    except requests.RequestException:
        return False
