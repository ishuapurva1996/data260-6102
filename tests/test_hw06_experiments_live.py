"""Live boundary tested with HTTP test doubles; no server/model is started."""
from copy import deepcopy
import json

import httpx
import pytest

from src.hw06_experiments.design import load_design
from src.hw06_experiments.live import HttpEndpoint, verify_gate, verify_model_identities
from src.hw06_experiments.runner import RequestFailed
from src.hw06_shared.config import HW6Config
from src.hw06_shared.contracts import ChatRequest
from src.hw06_shared.telemetry import RequestContext


def test_gate_rejects_foundation_only_and_wrong_frozen_source(tmp_path):
    config = HW6Config(source_commit="fixture", model_digest="m", embedding_digest="e")
    state = dict(source_commit="fixture", source_sha256="source-hash")
    hashes = load_design()[2]
    from src.hw06_experiments.design import digest
    gate = dict(live_integrated_ready=True, source_commit="fixture", source_sha256="source-hash",
                input_hashes=hashes, config_sha256=digest(config.public_dict()),
                file_memory_enabled=False, pilot=dict(n30_context_fit=True, no_prompt_truncation=True))
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate))
    verify_gate(path, config, state, hashes)
    for field, value in [("live_integrated_ready", False), ("source_sha256", "wrong"),
                         ("input_hashes", {}), ("file_memory_enabled", True),
                         ("pilot", dict(n30_context_fit=False, no_prompt_truncation=False))]:
        bad = deepcopy(gate)
        bad[field] = value
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            verify_gate(path, config, state, hashes)


def test_http_endpoint_sends_only_chat_body_and_correlation_headers():
    captured = []
    def handler(request):
        captured.append(request)
        if request.url.path.endswith("config"):
            return httpx.Response(200, json={"config": {"source_commit": "s"}, "source_commit": "s"})
        return httpx.Response(200, json={"reply": "fixture"})
    with httpx.Client(base_url="https://127.0.0.1:8702", transport=httpx.MockTransport(handler)) as client:
        endpoint = HttpEndpoint(client)
        assert endpoint.configuration() == {"source_commit": "s"}
        endpoint.chat(ChatRequest(user_id="7:hw6:fixture", session_id="s", message="hello"),
                      RequestContext(run_id="r", condition="A", turn_id=1, phase="primary"))
    assert json.loads(captured[1].content) == dict(user_id="7:hw6:fixture", session_id="s", message="hello")
    assert captured[1].headers["X-HW6-Phase"] == "primary"
    assert "X-HW6-Source-Commit" not in captured[1].headers


def test_http_error_keeps_real_code_and_does_not_turn_failure_into_reply():
    def handler(request):
        return httpx.Response(503, json={"detail": "Model unavailable", "code": "model_unavailable"})
    with httpx.Client(base_url="https://127.0.0.1:8702", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RequestFailed) as error:
            HttpEndpoint(client).chat(ChatRequest(user_id="u", message="hello"), RequestContext())
    assert error.value.status_code == 503 and error.value.code == "model_unavailable"


def test_model_digest_preflight_requires_installed_exact_identities():
    config = HW6Config(model_digest="m", embedding_digest="e")
    models = {"models": [{"name": config.model, "digest": "m"}, {"name": config.embedding_model, "digest": "e"}]}
    verify_model_identities(models, config)
    models["models"][0]["digest"] = "changed"
    with pytest.raises(ValueError):
        verify_model_identities(models, config)


def test_live_orchestrator_holds_one_lease_over_whole_study_without_live_work(tmp_path, monkeypatch):
    from src.hw06_experiments import live
    from src.hw06_experiments.design import digest
    from scripts.hw06.runtime_lease import RuntimeLease, LeaseBusy
    config = HW6Config(source_commit="fixture", model_digest="m", embedding_digest="e")
    state = dict(source_commit="fixture", source_sha256="source-hash")
    runtime = tmp_path / "canonical-runtime"
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps(dict(live_integrated_ready=True, **state,
                    input_hashes=load_design()[2], config_sha256=digest(config.public_dict()),
                    file_memory_enabled=False, pilot=dict(n30_context_fit=True, no_prompt_truncation=True))))
    monkeypatch.setattr(live, "RUNTIME_ROOT", runtime)
    monkeypatch.setattr(live, "source_state", lambda: state)
    monkeypatch.setattr(HW6Config, "from_env", classmethod(lambda cls: config))
    monkeypatch.setattr(live, "port_in_use", lambda: False)
    real_client = httpx.Client
    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"models": [
            {"name": config.model, "digest": "m"}, {"name": config.embedding_model, "digest": "e"}]})), **kwargs)
    monkeypatch.setattr(live.httpx, "Client", client)
    observed = []
    class DummyFactory:
        def __init__(self, **kwargs):
            assert kwargs["lease"].token
            observed.append(kwargs["lease"].token)
    class DummyRunner:
        def __init__(self, **kwargs):
            self.output = kwargs["output"]
            assert kwargs["evidence_kind"] == "measured_http"
        def run(self, **kwargs):
            owner = json.loads((runtime / "owner.json").read_text())
            assert owner["owner"] == "D" and owner["token"] == observed[0]
            with pytest.raises(LeaseBusy):
                RuntimeLease(runtime, owner="other", purpose="offline contention check").acquire()
            self.output.mkdir()
            # No measured request or filled result table is created by this spy.
            return dict(evidence_kind="offline_engineering_spy", status="no_requests")
    monkeypatch.setattr(live, "LiveFactory", DummyFactory)
    monkeypatch.setattr(live, "StudyRunner", DummyRunner)
    manifest = live.run_live(gate_path=gate, output=tmp_path / "spy", runtime_dir=runtime,
            env_files=[], cert=tmp_path / "unused", key=tmp_path / "unused", ca=tmp_path / "unused",
            owner_id="7", email="offline@example.com", password="offline")
    assert manifest["status"] == "no_requests"
    assert not (runtime / "owner.json").exists()
    assert len(observed) == 1
