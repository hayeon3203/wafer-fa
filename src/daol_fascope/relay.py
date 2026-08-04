import base64
import io
import os
from typing import Callable, TypedDict

import requests
from langgraph.graph import END, StateGraph
from PIL import Image

from daol_fascope.cases import search_cases

# The model itself lives in daol_fascope.llava_server, which runs in an
# OpenShell sandbox (docs/adr/0006). This process only speaks HTTP to it, so
# the relay stays light and keeps its own access to Qdrant/ThingsBoard.
LLAVA_URL = os.environ.get("LLAVA_URL", "http://localhost:8506")
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
TRANSLATE_MODEL = "exaone3.5:7.8b"
SEVERITY_LEVELS = ["CRITICAL", "MAJOR", "MINOR", "NONE"]
SEVERITY_KO = {
    "CRITICAL": "심각 (CRITICAL)",
    "MAJOR": "주요 (MAJOR)",
    "MINOR": "경미 (MINOR)",
    "NONE": "해당없음 (NONE)",
}

def generate(prompt: str, image: Image.Image | None = None, max_new_tokens: int = 200) -> str:
    payload = {"prompt": prompt, "max_new_tokens": max_new_tokens}
    if image is not None:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        payload["image_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
    # Long timeout: a cold sandbox is still loading 14GB, and a 200-token
    # generation on the wafer image is tens of seconds even when warm.
    response = requests.post(f"{LLAVA_URL}/generate", json=payload, timeout=300)
    response.raise_for_status()
    return response.json()["text"]


def translate_to_korean(text_en: str) -> str:
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={
            "model": TRANSLATE_MODEL,
            "prompt": (
                "Translate the following semiconductor fab defect-analysis text to "
                f"Korean. Output only the translation, no extra commentary.\n\n{text_en}"
            ),
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def parse_severity(text_en: str) -> str:
    upper = text_en.upper()
    for level in SEVERITY_LEVELS:
        if level in upper:
            return level
    return "MINOR"  # ponytail: no clear match, default to the middle level rather than raising


class RelayState(TypedDict):
    image: Image.Image
    defect_label: str
    confidence: float
    on_stage: Callable[[str], None] | None
    description_en: str
    root_cause_en: str
    severity_en: str
    recipe_en: str


def _enter_stage(state: RelayState, name: str) -> None:
    print(f"[relay] STAGE {name}", flush=True)
    if state.get("on_stage") is not None:
        state["on_stage"](name)


def describe_node(state: RelayState) -> dict:
    _enter_stage(state, "describe")
    prompt = (
        f"This is a semiconductor wafer map. The classifier predicted defect pattern "
        f"'{state['defect_label']}' with {state['confidence'] * 100:.1f}% confidence. "
        "Describe in 2-3 sentences what this defect pattern looks like on the wafer."
    )
    return {"description_en": generate(prompt, image=state["image"])}


def root_cause_node(state: RelayState) -> dict:
    _enter_stage(state, "root_cause")
    prompt = (
        f"A semiconductor wafer was classified with defect pattern '{state['defect_label']}'. "
        f"Description: {state['description_en']}\n"
        "List the most likely root cause(s) in the fab process for this defect pattern."
    )
    return {"root_cause_en": generate(prompt)}


def severity_node(state: RelayState) -> dict:
    _enter_stage(state, "severity")
    prompt = (
        f"Defect pattern: {state['defect_label']}. Root cause: {state['root_cause_en']}\n"
        "Classify the severity of this defect as exactly one of: "
        "CRITICAL, MAJOR, MINOR, NONE. Answer with just that one word."
    )
    return {"severity_en": parse_severity(generate(prompt, max_new_tokens=10))}


def recipe_node(state: RelayState) -> dict:
    _enter_stage(state, "recipe")
    similar = search_cases(f"{state['defect_label']} {state['root_cause_en']}")
    context = ""
    if similar:
        context = "Similar past cases:\n" + "\n".join(
            f"- {case}" for case in similar
        ) + "\n\n"
    prompt = (
        f"Defect pattern: {state['defect_label']}. Root cause: {state['root_cause_en']}. "
        f"Severity: {state['severity_en']}.\n"
        f"{context}"
        "Suggest a concrete corrective action or process recipe adjustment to address this defect."
    )
    return {"recipe_en": generate(prompt)}


_graph = None


def _build_graph():
    global _graph
    if _graph is None:
        builder = StateGraph(RelayState)
        builder.add_node("describe", describe_node)
        builder.add_node("root_cause", root_cause_node)
        builder.add_node("severity", severity_node)
        builder.add_node("recipe", recipe_node)
        builder.set_entry_point("describe")
        builder.add_edge("describe", "root_cause")
        builder.add_edge("root_cause", "severity")
        builder.add_edge("severity", "recipe")
        builder.add_edge("recipe", END)
        _graph = builder.compile()
    return _graph


def run_relay(
    image: Image.Image,
    defect_label: str,
    confidence: float,
    on_stage: Callable[[str], None] | None = None,
) -> dict:
    result = _build_graph().invoke(
        {"image": image, "defect_label": defect_label, "confidence": confidence, "on_stage": on_stage}
    )
    return {
        "description": translate_to_korean(result["description_en"]),
        "root_cause": translate_to_korean(result["root_cause_en"]),
        "severity": SEVERITY_KO[result["severity_en"]],
        "recipe": translate_to_korean(result["recipe_en"]),
    }
