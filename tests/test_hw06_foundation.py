"""Shared contracts are verified offline; these are not homework live evidence."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.hw06_shared.config import HW6Config
from src.hw06_shared.database import MongoConnection
from src.hw06_shared.models import usage_counts
from src.hw06_shared.serialization import json_value, parse_object_id
from src.hw06_shared.telemetry import CallEvent, RequestContext, TokenComponents
from scripts.hw06.runtime_lease import LeaseBusy, RuntimeLease


def test_fixed_configuration_and_experiment_overrides():
    config = HW6Config.from_env({"SHORT_TERM_N": "30", "HW6_POLICY": "token_budget"})
    assert (config.database_name, config.port, config.short_term_n) == ("s6102_doc", 8702, 30)
    assert config.policy == "token_budget"
    with pytest.raises(ValueError):
        HW6Config(database_name="other")
    with pytest.raises(ValueError):
        HW6Config(context_window=256, output_limit=512)


def test_one_lazy_mongo_database_and_safe_close():
    class Client:
        closed = False
        def __init__(self, *args, **kwargs):
            self.database = object()
        def __getitem__(self, name):
            assert name == "s6102_doc"
            return self.database
        def close(self):
            self.closed = True
    connection = MongoConnection(HW6Config(), client_factory=Client)
    assert connection.database is connection.database
    client = connection.client
    connection.close()
    connection.close()
    assert client.closed
    with pytest.raises(RuntimeError):
        _ = connection.database


def test_usage_absence_is_not_a_measured_zero():
    from src.model_client import OllamaModelClient
    response = SimpleNamespace(content="ok", usage_metadata={}, response_metadata={})
    client = OllamaModelClient(SimpleNamespace(invoke=lambda _: response))
    counts = usage_counts(client.complete([("user", "hello")]))
    assert counts.prompt_tokens is None and counts.completion_tokens is None
    response.response_metadata = {"prompt_eval_count": 0, "eval_count": 0}
    counts = usage_counts(client.complete([("user", "hello")]))
    assert counts.prompt_tokens == counts.completion_tokens == 0
    assert counts.usage_source == "model_reported"


def test_serialization_preserves_utc_and_ids():
    oid = parse_object_id("507f1f77bcf86cd799439011")
    assert json_value({"_id": oid, "at": datetime(2026, 1, 1, tzinfo=timezone.utc)}) == {
        "_id": str(oid), "at": "2026-01-01T00:00:00Z"}
    with pytest.raises(ValueError, match="Invalid document identifier"):
        parse_object_id("bad")
    with pytest.raises(ValueError, match="timezone"):
        json_value(datetime(2026, 1, 1))


def test_lease_cannot_be_stolen_or_released_by_a_different_owner(tmp_path):
    with RuntimeLease(tmp_path, owner="A", purpose="test") as lease:
        with pytest.raises(LeaseBusy):
            RuntimeLease(tmp_path, owner="D", purpose="benchmark").acquire()
        assert lease.token
    with RuntimeLease(tmp_path, owner="D", purpose="benchmark"):
        pass
    assert not (tmp_path / "owner.json").exists()


def test_telemetry_missing_counts_and_signed_template_residual():
    context = RequestContext(request_id="r", run_id="run", probe_id="p", condition="N12")
    event = CallEvent(context=context, kind="request", operation="chat",
                      started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                      user_id="1", session_id="s", latency_ms=4,
                      components=TokenComponents(system=8, window=9, current_message=2,
                                                 template_residual=-1),
                      prompt_tokens=18, completion_tokens=3, usage_source="model_reported")
    assert event.model_dump(mode="json")["context"]["probe_id"] == "p"
    assert event.components.template_residual == -1
    with pytest.raises(ValueError):
        CallEvent(context=context, kind="embedding", operation="query", user_id="1",
                  session_id="s", started_at=datetime.now(timezone.utc), latency_ms=-1)


def test_authentication_scope_includes_only_owners_experiment_namespace():
    from fastapi import HTTPException
    from src.hw06_shared.contracts import authorize_memory_user
    owner = SimpleNamespace(id=7)
    authorize_memory_user("7", owner)
    authorize_memory_user("7:hw6:N12:unique", owner)
    with pytest.raises(HTTPException) as exc:
        authorize_memory_user("70:hw6:N12:unique", owner)
    assert exc.value.status_code == 403


def test_sanitized_service_error_cannot_leak_connection_details():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.hw06_shared.errors import StorageUnavailable, install_error_handlers
    app = FastAPI()
    install_error_handlers(app)
    @app.get("/probe")
    def probe():
        raise StorageUnavailable("PRIVATE_SENTINEL")
    with TestClient(app) as client:
        response = client.get("/probe")
    assert response.status_code == 503
    assert "PRIVATE_SENTINEL" not in response.text
    assert response.json()["code"] == "storage_unavailable"


def test_jsonl_roundtrip_exposes_validated_event_to_experiment_reader(tmp_path):
    import json
    from src.hw06_shared.telemetry import JsonlTelemetry
    sink = JsonlTelemetry(tmp_path / "events.jsonl")
    event = CallEvent(context=RequestContext(), kind="generation", operation="extraction",
                      user_id="1", session_id="s", started_at=datetime.now(timezone.utc),
                      latency_ms=1.5, usage_source="missing")
    sink.emit(event)
    restored = CallEvent.model_validate(json.loads(sink.path.read_text()))
    assert restored == event
    assert restored.prompt_tokens is None


def test_adapter_options_are_central_and_legacy_defaults_stay_compatible(monkeypatch):
    import langchain_ollama
    from src.model_client import build_ollama_client
    observed = []
    monkeypatch.setattr(langchain_ollama, "ChatOllama", lambda **kw: observed.append(kw))
    build_ollama_client("qwen2.5:7b", "http://localhost:11434", 0, 10)
    build_ollama_client("qwen2.5:7b", "http://localhost:11434", 0, 10,
                        context_window=8192, output_limit=256, seed=6102)
    assert observed[0]["num_ctx"] == 4096 and "num_predict" not in observed[0]
    assert (observed[1]["num_ctx"], observed[1]["num_predict"], observed[1]["seed"]) == (8192, 256, 6102)


def test_environment_accepts_fixed_numeric_values_and_rejects_drift():
    config = HW6Config.from_env({"HW6_SID4": "6102", "HW6_SEED": "6102", "HW6_PORT": "8702"})
    assert config.sid4 == config.seed == 6102
    with pytest.raises(ValueError):
        HW6Config.from_env({"HW6_SEED": "123"})


@pytest.mark.parametrize("changes", [
    {"usage_source": "model_reported"},
    {"usage_source": "missing", "prompt_tokens": 0},
    {"kind": "embedding", "operation": "chat"},
])
def test_telemetry_rejects_mislabelled_usage_and_operations(changes):
    values = dict(context=RequestContext(), kind="request", operation="chat",
                  user_id="1", session_id="s", started_at=datetime.now(timezone.utc),
                  latency_ms=1)
    with pytest.raises(ValueError):
        CallEvent(**{**values, **changes})
