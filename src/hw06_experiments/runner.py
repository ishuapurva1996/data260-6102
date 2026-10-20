"""Sequential study orchestration with injected endpoints and optional clones.

This module never constructs a model or writes memory directly. The live command
owns one RuntimeLease around the entire study, including child app lifetimes.
"""
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from src.hw06_shared.config import HW6Config
from src.hw06_shared.contracts import ChatRequest, ChatResponse
from src.hw06_shared.telemetry import RequestContext
from .design import CONDITIONS, ROOT, digest, load_design


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def append_json(path: Path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class Endpoint(Protocol):
    def configuration(self) -> dict: ...
    def chat(self, request: ChatRequest, context: RequestContext) -> dict: ...


class ProbeIsolation(Protocol):
    """Implement only with a complete messages/summaries/episodes snapshot.

    snapshot captures after primary turn 30; clone remaps every user/session/id
    reference into a fresh owner-prefixed namespace. Base state stays unchanged.
    No partial inspection-endpoint snapshot qualifies (it truncates history).
    """
    def snapshot(self, endpoint: Endpoint, user_id: str, session_id: str) -> str: ...
    def clone(self, snapshot_id: str, user_id: str, session_id: str) -> AbstractContextManager: ...


class RequestFailed(RuntimeError):
    """A logged HTTP failure; body must be the server's sanitized public JSON."""
    def __init__(self, status_code: int | None, response: dict, code: str):
        super().__init__(code)
        self.status_code, self.response, self.code = status_code, response, code


class StudyRunner:
    def __init__(self, *, base_config: HW6Config, owner_id: str,
                 endpoint_factory: Callable, output: Path, design_root: Path = ROOT,
                 evidence_kind: str = "offline_engineering", isolation: ProbeIsolation | None = None,
                 timer=perf_counter):
        self.base_config, self.owner_id = base_config, owner_id
        self.endpoint_factory, self.output = endpoint_factory, Path(output)
        self.design_root, self.isolation, self.timer = design_root, isolation, timer
        if evidence_kind not in {"offline_engineering", "measured_http"}:
            raise ValueError("Unknown evidence kind")
        self.evidence_kind = evidence_kind

    def identity(self, condition: str):
        suffix = uuid4().hex
        return (f"{self.owner_id}:hw6:D:{condition}:{suffix}",
                f"{self.owner_id}:hw6:D:session:{condition}:{uuid4().hex}")

    def run(self, *, provenance: dict | None = None):
        conversation, probes, hashes = load_design(self.design_root)
        self.output.mkdir(parents=True, exist_ok=False)  # never overwrite an attempt
        (self.output / "conversation.json").write_bytes((self.design_root / "scripts/hw06/part3/conversation.json").read_bytes())
        (self.output / "memory_probes.yaml").write_bytes((self.design_root / "memory_probes.yaml").read_bytes())
        run_id = "s6102-D-" + uuid4().hex
        manifest = dict(schema_version="hw06.study.v1", run_id=run_id,
                        evidence_kind=self.evidence_kind, status="running", input_hashes=hashes,
                        counting_convention=conversation["counting_convention"],
                        base_config=self.base_config.public_dict(),
                        source_commit=self.base_config.source_commit,
                        provenance=provenance or {}, warmup="none; identical for all conditions",
                        file_memory_enabled=False,
                        probe_isolation="snapshot_clone" if self.isolation else "sequential_fixed_order",
                        sequential_probe_effects=(None if self.isolation else
                            "Earlier probes and their answers persist and may affect later probes, summaries and episodes. Order is fixed."),
                        expected_primary_calls=120, expected_probe_calls=20, conditions=[])
        write_json(self.output / "manifest.json", manifest)
        try:
            for condition in CONDITIONS:
                directory = self.output / condition.id
                directory.mkdir()
                config = condition.configure(self.base_config)
                user_id, session_id = self.identity(condition.id)
                record = dict(id=condition.id, label=condition.label, user_id=user_id,
                              session_id=session_id, config=config.public_dict(),
                              config_sha256=digest(config.public_dict()), probe_clones=[])
                manifest["conditions"].append(record)
                write_json(self.output / "manifest.json", manifest)
                with self.endpoint_factory(config, directory) as endpoint:
                    actual = endpoint.configuration()
                    write_json(directory / "server_config.json", actual)
                    if actual != config.public_dict():
                        raise ValueError("Integrated app configuration differs from frozen condition")
                    for turn, message in enumerate(conversation["messages"], 1):
                        self._call(endpoint, directory, config, run_id, condition.id, user_id,
                                   session_id, message, phase="primary", turn_id=turn)
                    snapshot = self.isolation.snapshot(endpoint, user_id, session_id) if self.isolation else None
                    record["snapshot_id"] = snapshot
                    for probe in probes["probes"]:
                        if self.isolation:
                            probe_user, probe_session = self.identity(condition.id + "-" + probe["id"])
                            record["probe_clones"].append(dict(probe_id=probe["id"], user_id=probe_user,
                                                               session_id=probe_session, snapshot_id=snapshot))
                            write_json(self.output / "manifest.json", manifest)
                            with self.isolation.clone(snapshot, probe_user, probe_session):
                                self._call(endpoint, directory, config, run_id, condition.id, probe_user,
                                           probe_session, probe["question"], phase="probe", probe_id=probe["id"])
                        else:
                            self._call(endpoint, directory, config, run_id, condition.id, user_id,
                                       session_id, probe["question"], phase="probe", probe_id=probe["id"])
            manifest["status"] = "collected_unvalidated_unscored"
        except BaseException as exc:
            manifest["status"] = "incomplete"
            manifest["failure"] = dict(type=type(exc).__name__, code=getattr(exc, "code", None))
            raise
        finally:
            write_json(self.output / "manifest.json", manifest)
        return manifest

    def _call(self, endpoint, directory, config, run_id, condition, user_id, session_id,
              message, *, phase, turn_id=None, probe_id=None):
        context = RequestContext(run_id=run_id, condition=condition, phase=phase, turn_id=turn_id,
                                 probe_id=probe_id, source_commit=config.source_commit)
        request = ChatRequest(user_id=user_id, session_id=session_id, message=message)
        row = dict(context=context.model_dump(mode="json"), request=request.model_dump(),
                   started_at=datetime.now(timezone.utc).isoformat(),
                   config_sha256=digest(config.public_dict()), status="started",
                   timing_scope="http_endpoint" if self.evidence_kind == "measured_http" else "injected_endpoint")
        append_json(directory / "attempts.jsonl", row)
        started = self.timer()
        try:
            response = endpoint.chat(request, context)
            row["response"] = response  # retain even if schema/identity validation fails
            reply = ChatResponse.model_validate(response)
            if (reply.user_id, reply.session_id, reply.request_id) != (user_id, session_id, context.request_id):
                raise ValueError("Reply identity differs from submitted request")
            if not reply.reply.strip():
                raise ValueError("Empty reply")
            row.update(status="ok", http_status=200)
        except BaseException as exc:
            row.update(status="error", error_type=type(exc).__name__,
                       error_code=getattr(exc, "code", "client_validation_or_transport_error"),
                       http_status=getattr(exc, "status_code", None))
            if isinstance(exc, RequestFailed):
                row["response"] = exc.response
            raise
        finally:
            row["http_latency_ms"] = (self.timer() - started) * 1000
            append_json(directory / "requests.jsonl", row)
