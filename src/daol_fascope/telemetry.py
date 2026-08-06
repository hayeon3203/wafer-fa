import os

import requests

THINGSBOARD_URL = os.environ.get("THINGSBOARD_URL", "http://localhost:8082")
THINGSBOARD_DEVICE_TOKEN = os.environ.get("THINGSBOARD_DEVICE_TOKEN", "")


def _post(payload: dict) -> bool:
    if not THINGSBOARD_DEVICE_TOKEN:
        print(
            f"[telemetry] THINGSBOARD_DEVICE_TOKEN not set, dropping telemetry keys={sorted(payload)}",
            flush=True,
        )
        return False
    try:
        resp = requests.post(
            f"{THINGSBOARD_URL}/api/v1/{THINGSBOARD_DEVICE_TOKEN}/telemetry",
            json=payload,
            timeout=5,
        )
        if not resp.ok:
            print(
                f"[telemetry] POST failed status={resp.status_code} body={resp.text[:200]!r} keys={sorted(payload)}",
                flush=True,
            )
        return resp.ok
    except requests.RequestException as exc:
        print(f"[telemetry] POST error: {exc} keys={sorted(payload)}", flush=True)
        return False


def send_pipeline_stage(stage: str, error_node: str | None = None) -> bool:
    """POST the current pipeline_stage for the ThingsBoard Detail dashboard's progress bar."""
    payload = {"pipeline_stage": stage}
    if error_node is not None:
        payload["pipeline_stage_error_node"] = error_node
    return _post(payload)


def send_run_started(
    *,
    run_id,
    lot_id,
    wafer_index,
    wafer_image_b64,
    die_yield,
    started_at,
) -> bool:
    """POST the wafer identity as soon as it's picked, before classify/relay run.

    Sent as its own payload (ahead of classify) so the "Wafer Yield Map" widget
    always shows the wafer this run picked even if classify or relay later fails
    -- and result_status=running lets the dashboard hide the previous run's
    description/root_cause/severity/recipe until this run's own results land.
    """
    return _post({
        "run_id": run_id,
        "lot_id": lot_id,
        "wafer_index": wafer_index,
        "wafer_image": wafer_image_b64,
        "die_yield": die_yield,
        "die_yield_pct": die_yield * 100,
        "pipeline_stage": "classify",
        "result_status": "running",
        "started_at": started_at,
    })


def send_run_error(
    *,
    run_id,
    lot_id,
    wafer_index,
    error_node,
    error_message,
) -> bool:
    """POST a failed run -- same run_id/lot_id/wafer_index as send_run_started so
    the dashboard keeps showing the picked wafer while flagging the failure."""
    return _post({
        "run_id": run_id,
        "lot_id": lot_id,
        "wafer_index": wafer_index,
        "pipeline_stage": "error",
        "pipeline_stage_error_node": error_node,
        "result_status": "error",
        "error_message": error_message,
    })


def send_classification_telemetry(
    *,
    run_id=None,
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
    completed_at=None,
) -> bool:
    """POST one classification + relay result to the ThingsBoard demo dashboard device.

    Optional integration: returns False (never raises) if THINGSBOARD_DEVICE_TOKEN
    isn't set or the request fails, so the classifier demo works with ThingsBoard down.
    """
    payload = {
        "lot_id": lot_id,
        "wafer_index": wafer_index,
        "defect_class": defect_label,
        "confidence": confidence,
        "pipeline_stage": "done",
        "result_status": "done",
        **{f"prob_{k}": v for k, v in probs.items()},
    }
    if run_id is not None:
        payload["run_id"] = run_id
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
    if completed_at is not None:
        payload["completed_at"] = completed_at
    return _post(payload)


def send_equipment_snapshot(readings: list[tuple[str, float]]) -> bool:
    """POST one wafer's full sensor snapshot as a single telemetry payload
    (Kafka streaming smoketest, 2026-07-24 design) -- one POST per wafer,
    not one per sensor, so ThingsBoard's HTTP round-trip time doesn't become
    the bottleneck the smoke test is trying to measure."""
    payload = {param: value for param, value in readings}
    return _post(payload)
