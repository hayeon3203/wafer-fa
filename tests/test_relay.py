from PIL import Image

from wafer_fa import relay


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
