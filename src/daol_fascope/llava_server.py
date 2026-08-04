"""LLaVA generation server -- the only process that holds the ~14GB model.

Split out of relay.py so the model can be isolated in an OpenShell sandbox
while the LangGraph relay keeps running on the host. The relay cannot move
into the sandbox with it: sandbox egress is denied by policy (every outbound
call returns 403), and the relay has to reach Qdrant :6333, ThingsBoard :8082
and Ollama :11434. A model server is a leaf -- it only answers -- so it is the
part that can be locked up. See docs/adr/0006.

Run: python -m daol_fascope.llava_server
"""
import base64
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from PIL import Image
from transformers import LlavaForConditionalGeneration, LlavaProcessor

LLAVA_MODEL = "llava-hf/llava-1.5-7b-hf"
HOST = os.environ.get("LLAVA_HOST", "127.0.0.1")
PORT = int(os.environ.get("LLAVA_PORT", "8506"))

_model = None
_processor = None
# ponytail: one model on one GPU -- serialize instead of batching. The demo
# pipeline is already single-flight upstream (wafer_predict_server holds a
# lock), this only guards against a second caller.
_gpu_lock = threading.Lock()


def load():
    global _model, _processor
    if _model is None:
        _processor = LlavaProcessor.from_pretrained(LLAVA_MODEL)
        _model = LlavaForConditionalGeneration.from_pretrained(
            LLAVA_MODEL, dtype=torch.bfloat16, device_map="auto"
        )
        _model.eval()
    return _model, _processor


def generate(prompt: str, image: Image.Image | None = None, max_new_tokens: int = 200) -> str:
    model, processor = load()
    with _gpu_lock:
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


def parse_request(body: bytes) -> dict:
    """Decode a /generate request body into generate() kwargs.

    Kept separate from the handler so the wire format is testable without a
    GPU or a socket.
    """
    payload = json.loads(body)
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("prompt is required")
    image_b64 = payload.get("image_b64")
    image = None
    if image_b64:
        image = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    return {
        "prompt": prompt,
        "image": image,
        "max_new_tokens": int(payload.get("max_new_tokens", 200)),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # ponytail: quiet by default; remove to debug requests

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self._send_json({"error": "not found"}, 404)
            return
        # Deliberately does not touch the model: the sandbox readiness probe
        # must answer while the 14GB load is still in flight.
        self._send_json({"status": "ok", "backend": "llava", "loaded": _model is not None})

    def do_POST(self):
        if self.path != "/generate":
            self._send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            kwargs = parse_request(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            self._send_json({"error": f"bad request: {exc}"}, 400)
            return
        try:
            self._send_json({"text": generate(**kwargs)})
        except Exception as exc:
            print(f"[llava_server] generate failed: {exc}", flush=True)
            self._send_json({"error": str(exc)}, 500)


def main():
    # Load before listening. The relay expects a warm model (ADR 0005); a cold
    # first request would otherwise eat the 14GB load time inside a pipeline run.
    print(f"llava_server loading {LLAVA_MODEL}...", flush=True)
    load()
    print(f"llava_server listening on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
