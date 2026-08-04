import base64
import io

from PIL import Image

from daol_fascope import relay


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_generate_posts_to_llava_server_and_returns_text(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        return _FakeResponse({"text": "a ring near the edge"})

    monkeypatch.setattr(relay.requests, "post", fake_post)

    assert relay.generate("describe this", max_new_tokens=10) == "a ring near the edge"
    assert sent["url"] == f"{relay.LLAVA_URL}/generate"
    assert sent["json"] == {"prompt": "describe this", "max_new_tokens": 10}


def test_generate_sends_image_as_base64_png(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(json)
        return _FakeResponse({"text": "ok"})

    monkeypatch.setattr(relay.requests, "post", fake_post)
    relay.generate("look", image=Image.new("RGB", (8, 8), (0, 255, 0)))

    decoded = Image.open(io.BytesIO(base64.b64decode(sent["image_b64"])))
    assert decoded.size == (8, 8)
    assert decoded.format == "PNG"


def test_parse_severity_matches_known_levels():
    assert relay.parse_severity("this is CRITICAL damage") == "CRITICAL"
    assert relay.parse_severity("looks minor, MAJOR concern") == "MAJOR"
    assert relay.parse_severity("no defect, none found") == "NONE"
    assert relay.parse_severity("unparseable gibberish") == "MINOR"


def test_run_relay_threads_state_through_all_four_agents(monkeypatch):
    calls = []

    def fake_generate(prompt, image=None, max_new_tokens=200):
        calls.append(prompt)
        if "Describe" in prompt:
            return "a ring-shaped defect near the wafer edge"
        if "Classify the severity" in prompt:
            return "MAJOR"
        if "List the most likely root cause" in prompt:
            return "etch process misalignment"
        return "recalibrate the etch tool alignment"

    monkeypatch.setattr(relay, "generate", fake_generate)
    monkeypatch.setattr(relay, "translate_to_korean", lambda text_en: f"[ko]{text_en}")
    monkeypatch.setattr(relay, "search_cases", lambda query, top_k=3: [])

    image = Image.new("RGB", (224, 224))
    result = relay.run_relay(image, defect_label="Edge-Ring", confidence=0.87)

    assert result["description"] == "[ko]a ring-shaped defect near the wafer edge"
    assert result["root_cause"] == "[ko]etch process misalignment"
    assert result["severity"] == relay.SEVERITY_KO["MAJOR"]
    assert result["recipe"] == "[ko]recalibrate the etch tool alignment"

    # root_cause node must see describe node's output; recipe node must see severity's
    assert any("a ring-shaped defect near the wafer edge" in c for c in calls[1:2])
    assert any("MAJOR" in c for c in calls[3:4])


def test_run_relay_calls_on_stage_for_each_node_in_order(monkeypatch):
    monkeypatch.setattr(relay, "generate", lambda prompt, image=None, max_new_tokens=200: "x")
    monkeypatch.setattr(relay, "translate_to_korean", lambda text_en: text_en)
    monkeypatch.setattr(relay, "search_cases", lambda query, top_k=3: [])

    stages = []
    image = Image.new("RGB", (224, 224))
    relay.run_relay(image, defect_label="Center", confidence=0.9, on_stage=stages.append)

    assert stages == ["describe", "root_cause", "severity", "recipe"]


def test_run_relay_without_on_stage_still_works(monkeypatch):
    monkeypatch.setattr(relay, "generate", lambda prompt, image=None, max_new_tokens=200: "x")
    monkeypatch.setattr(relay, "translate_to_korean", lambda text_en: text_en)
    monkeypatch.setattr(relay, "search_cases", lambda query, top_k=3: [])

    image = Image.new("RGB", (224, 224))
    result = relay.run_relay(image, defect_label="Center", confidence=0.9)
    assert result["description"] == "x"
