from typing import TypedDict

import requests
import torch
from langgraph.graph import END, StateGraph
from PIL import Image
from transformers import LlavaForConditionalGeneration, LlavaProcessor

from wafer_fa.cases import search_cases

LLAVA_MODEL = "llava-hf/llava-1.5-7b-hf"
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
TRANSLATE_MODEL = "exaone3.5:7.8b"
SEVERITY_LEVELS = ["CRITICAL", "MAJOR", "MINOR", "NONE"]
SEVERITY_KO = {
    "CRITICAL": "심각 (CRITICAL)",
    "MAJOR": "주요 (MAJOR)",
    "MINOR": "경미 (MINOR)",
    "NONE": "해당없음 (NONE)",
}

_model = None
_processor = None


def _load_llava():
    global _model, _processor
    if _model is None:
        _processor = LlavaProcessor.from_pretrained(LLAVA_MODEL)
        _model = LlavaForConditionalGeneration.from_pretrained(
            LLAVA_MODEL, dtype=torch.bfloat16, device_map="auto"
        )
        _model.eval()
    return _model, _processor


def generate(prompt: str, image: Image.Image | None = None, max_new_tokens: int = 200) -> str:
    model, processor = _load_llava()
    if image is not None:
        full_prompt = f"USER: <image>\n{prompt}\nASSISTANT:"
        inputs = processor(text=full_prompt, images=image, return_tensors="pt").to(model.device)
    else:
        full_prompt = f"USER: {prompt}\nASSISTANT:"
        inputs = processor(text=full_prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    text = processor.decode(output[0], skip_special_tokens=True)
    return text.rsplit("ASSISTANT:", 1)[-1].strip()


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
    description_en: str
    root_cause_en: str
    severity_en: str
    recipe_en: str


def describe_node(state: RelayState) -> dict:
    print("[relay] STAGE describe", flush=True)
    prompt = (
        f"This is a semiconductor wafer map. The classifier predicted defect pattern "
        f"'{state['defect_label']}' with {state['confidence'] * 100:.1f}% confidence. "
        "Describe in 2-3 sentences what this defect pattern looks like on the wafer."
    )
    return {"description_en": generate(prompt, image=state["image"])}


def root_cause_node(state: RelayState) -> dict:
    print("[relay] STAGE root_cause", flush=True)
    prompt = (
        f"A semiconductor wafer was classified with defect pattern '{state['defect_label']}'. "
        f"Description: {state['description_en']}\n"
        "List the most likely root cause(s) in the fab process for this defect pattern."
    )
    return {"root_cause_en": generate(prompt)}


def severity_node(state: RelayState) -> dict:
    print("[relay] STAGE severity", flush=True)
    prompt = (
        f"Defect pattern: {state['defect_label']}. Root cause: {state['root_cause_en']}\n"
        "Classify the severity of this defect as exactly one of: "
        "CRITICAL, MAJOR, MINOR, NONE. Answer with just that one word."
    )
    return {"severity_en": parse_severity(generate(prompt, max_new_tokens=10))}


def recipe_node(state: RelayState) -> dict:
    print("[relay] STAGE recipe", flush=True)
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


def run_relay(image: Image.Image, defect_label: str, confidence: float) -> dict:
    result = _build_graph().invoke(
        {"image": image, "defect_label": defect_label, "confidence": confidence}
    )
    return {
        "description": translate_to_korean(result["description_en"]),
        "root_cause": translate_to_korean(result["root_cause_en"]),
        "severity": SEVERITY_KO[result["severity_en"]],
        "recipe": translate_to_korean(result["recipe_en"]),
    }
