from fastapi.testclient import TestClient

from app.main import app


def test_agent_improvement_plan_is_practical_and_read_only(client: TestClient, monkeypatch):
    monkeypatch.delenv("EVAL_GATE", raising=False)
    monkeypatch.delenv("SELF_IMPROVE_LOOP", raising=False)

    r = client.get("/api/ml/improvement-plan")
    assert r.status_code == 200
    data = r.json()

    assert data["success"] is True
    assert data["name"] == "Agent Improvement Loop"
    assert "RAG + eval" in data["production_rule"]

    phase_keys = [p["key"] for p in data["phases"]]
    assert phase_keys == ["rag_first", "eval_loop", "prompt_tool_tuning", "lora_later"]

    lora = data["phases"][-1]
    assert lora["status"] in {"wait_for_data", "ready"}
    assert "LoRA" in lora["title"]
    assert "paid Vertex" in " ".join(data["free_gpu_policy"]["do_not_use_for"])


def test_agent_improvement_plan_reflects_eval_flag(client: TestClient, monkeypatch):
    monkeypatch.setenv("EVAL_GATE", "1")

    r = client.get("/api/ml/improvement-plan")
    assert r.status_code == 200
    data = r.json()

    assert data["current_stack"]["eval_gate_enabled"] is True
    eval_phase = [p for p in data["phases"] if p["key"] == "eval_loop"][0]
    assert eval_phase["status"] == "ready"
