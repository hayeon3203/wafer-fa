import os

import requests

THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8082")
THINGSBOARD_DEVICE_TOKEN = os.environ.get("THINGSBOARD_DEVICE_TOKEN", "")


def send_classification_telemetry(
    *,
    lot_id,
    wafer_index,
    defect_label,
    confidence,
    probs,
    die_yield=None,
    description=None,
    root_cause=None,
    severity=None,
    recipe=None,
    wafer_image_b64=None,
) -> bool:
    """POST one classification + relay result to the ThingsBoard demo dashboard device.

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
    if die_yield is not None:
        payload["die_yield"] = die_yield
        payload["die_yield_pct"] = die_yield * 100
    if description is not None:
        payload["description"] = description
    if root_cause is not None:
        payload["root_cause"] = root_cause
    if severity is not None:
        payload["severity"] = severity
    if recipe is not None:
        payload["recipe"] = recipe
    if wafer_image_b64 is not None:
        payload["wafer_image"] = wafer_image_b64
    try:
        resp = requests.post(
            f"{THINGSBOARD_URL}/api/v1/{THINGSBOARD_DEVICE_TOKEN}/telemetry",
            json=payload,
            timeout=5,
        )
        return resp.ok
    except requests.RequestException:
        return False
