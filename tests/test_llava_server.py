import base64
import io
import json

import pytest
from PIL import Image

from daol_fascope import llava_server


def _png_b64(size=(8, 8), color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_parse_request_text_only():
    kwargs = llava_server.parse_request(json.dumps({"prompt": "hello"}).encode())
    assert kwargs == {"prompt": "hello", "image": None, "max_new_tokens": 200}


def test_parse_request_decodes_image_and_max_tokens():
    body = json.dumps({"prompt": "look", "image_b64": _png_b64(), "max_new_tokens": 10}).encode()
    kwargs = llava_server.parse_request(body)
    assert kwargs["max_new_tokens"] == 10
    assert kwargs["image"].size == (8, 8)
    assert kwargs["image"].mode == "RGB"


def test_parse_request_rejects_missing_prompt():
    with pytest.raises(ValueError):
        llava_server.parse_request(json.dumps({"image_b64": _png_b64()}).encode())
    with pytest.raises(ValueError):
        llava_server.parse_request(json.dumps({"prompt": ""}).encode())
