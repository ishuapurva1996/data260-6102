"""Validate C's authoritative events and join them to durable client records."""
import json
import math
from pathlib import Path

import yaml

from src.hw06_shared.contracts import render_window
from src.hw06_shared.telemetry import CallEvent
from .design import CONDITIONS, CONVERSATION, PROBES, digest, file_hash
from .runner import read_jsonl

BLOCKS = ("system", "session_summary", "lifetime_summary", "window", "episodes", "current_message")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_study(directory: Path, *, count_tokens=None):
    """Returns joined records; never zero-fills errors, missing usage or events.

    Raw failed attempts remain in their original directory. Invalid conditions
    cannot be selectively dropped to produce a seemingly complete study.
    """
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["status"] == "collected_unvalidated_unscored", "Study is incomplete")
    if manifest["evidence_kind"] == "measured_http":
        postflight = json.loads((directory / "postflight.json").read_text())
        require(postflight.get("source_unchanged") is True, "Measured study postflight missing")
        require(bool(manifest["provenance"].get("source_sha256")), "Measured source hash missing")
    for original, snapshot in ((CONVERSATION, "conversation.json"), (PROBES, "memory_probes.yaml")):
        require(file_hash(directory / snapshot) == manifest["input_hashes"][str(original)],
                "Frozen input snapshot hash mismatch")
    conversation = json.loads((directory / "conversation.json").read_text())
    probes = yaml.safe_load((directory / "memory_probes.yaml").read_text())
    require([c["id"] for c in manifest["conditions"]] == [c.id for c in CONDITIONS], "Four conditions required")
    users, sessions, request_ids, event_ids = set(), set(), set(), set()
    joined = {}
    for spec, condition in zip(CONDITIONS, manifest["conditions"], strict=True):
        cfg = condition["config"]
        require(cfg["short_term_n"] == spec.n and cfg["policy"] == spec.policy and cfg["token_budget"] == 160,
                "Condition configuration mismatch")
        base = {k: v for k, v in manifest["base_config"].items() if k not in {"short_term_n", "policy", "token_budget"}}
        require(all(cfg[k] == v for k, v in base.items()), "Controls differ across conditions")
        require(condition["config_sha256"] == digest(cfg), "Condition hash mismatch")
        require(cfg["source_commit"] == manifest["source_commit"], "Source revision mismatch")
        all_identities = [(condition["user_id"], condition["session_id"])]
        all_identities += [(c["user_id"], c["session_id"]) for c in condition["probe_clones"]]
        require(len(condition["probe_clones"]) == (5 if manifest["probe_isolation"] == "snapshot_clone" else 0),
                "Wrong number of probe clones")
        for user, session in all_identities:
            require(user not in users and session not in sessions, "Condition/probe identities reused")
            users.add(user)
            sessions.add(session)
        path = directory / spec.id
        require(json.loads((path / "server_config.json").read_text()) == cfg, "Server configuration drift")
        rows, attempts = read_jsonl(path / "requests.jsonl"), read_jsonl(path / "attempts.jsonl")
        require(len(rows) == len(attempts) == 35, "Need 30 primary and five probe requests, without retries")
        require([r["context"]["request_id"] for r in rows] == [a["context"]["request_id"] for a in attempts],
                "Unfinished or reordered request attempt")
        events = [CallEvent.model_validate(raw) for raw in read_jsonl(path / "events.jsonl")]
        grouped = {}
        for event in events:
            require(event.event_id not in event_ids, "Duplicate event ID")
            event_ids.add(event.event_id)
            grouped.setdefault(event.context.request_id, []).append(event)
        require(set(grouped) == {r["context"]["request_id"] for r in rows}, "Missing or orphan event correlation")
        results = []
        for index, (row, attempt) in enumerate(zip(rows, attempts, strict=True)):
            ctx, request = row["context"], row["request"]
            rid = ctx["request_id"]
            require(rid not in request_ids, "Duplicate request ID")
            request_ids.add(rid)
            require(row["status"] == "ok" and row.get("http_status") == 200, "Failed request retained; study incomplete")
            elapsed = row.get("http_latency_ms")
            require(isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0,
                    "Invalid HTTP latency")
            require(row["timing_scope"] == ("http_endpoint" if manifest["evidence_kind"] == "measured_http" else "injected_endpoint"),
                    "Timing scope mislabelled")
            require(attempt["request"] == request and attempt["context"] == ctx, "Submitted request changed")
            require(row["config_sha256"] == digest(cfg), "Client configuration drift")
            require(ctx["run_id"] == manifest["run_id"] and ctx["condition"] == spec.id, "Wrong request correlation")
            require(ctx["source_commit"] == manifest["source_commit"], "Wrong client source revision")
            if index < 30:
                require((ctx["phase"], ctx["turn_id"], ctx["probe_id"]) == ("primary", index + 1, None), "Primary order changed")
                expected_message = conversation["messages"][index]
                identity = condition
            else:
                probe = probes["probes"][index - 30]
                require((ctx["phase"], ctx["turn_id"], ctx["probe_id"]) == ("probe", None, probe["id"]), "Probe order changed")
                expected_message = probe["question"]
                identity = (condition["probe_clones"][index - 30]
                            if manifest["probe_isolation"] == "snapshot_clone" else condition)
                if manifest["probe_isolation"] == "snapshot_clone":
                    require(identity["probe_id"] == probe["id"] and
                            identity["snapshot_id"] == condition["snapshot_id"], "Probe snapshot mismatch")
            require(request["message"] == expected_message, "Frozen message differs")
            require((request["user_id"], request["session_id"]) == (identity["user_id"], identity["session_id"]), "Wrong namespace")
            response = row["response"]
            require((response["user_id"], response["session_id"], response["request_id"]) ==
                    (request["user_id"], request["session_id"], rid), "Wrong response identity")
            correlated = grouped[rid]
            main = [e for e in correlated if e.kind == "request"]
            require(len(main) == 1, "Exactly one request/chat event required")
            for event in correlated:
                require(event.context.model_dump(mode="json") == ctx, "Event context mismatch")
                require((event.user_id, event.session_id) == (request["user_id"], request["session_id"]), "Event identity mismatch")
                require(event.status == "ok" and event.error_code is None, "Failed event retained; study incomplete")
                require(all(event.config.get(k) == v for k, v in cfg.items()), "Event configuration drift")
                require(not event.config.get("file_memory_enabled", False), "File memory is prohibited")
                if event.kind == "embedding":
                    require(event.usage_source == "not_applicable" and
                            event.embedding_dimension == cfg["embedding_dimension"] and
                            event.input_count is not None, "Invalid embedding record")
                else:
                    require(event.usage_source == "model_reported", "Missing model usage invalidates condition")
                    require(event.total_tokens in (None, event.prompt_tokens + event.completion_tokens), "Token total mismatch")
            event = main[0]
            require(event.components is not None and event.component_text is not None, "Prompt components missing")
            components, texts = event.components, event.component_text
            require(components.count_method == "model_tokenizer_text_estimate" and bool(components.tokenizer_identity), "Tokenizer identity missing")
            if cfg["tokenizer_sha256"]:
                require(components.tokenizer_identity.endswith(cfg["tokenizer_sha256"]), "Wrong component tokenizer")
            require(components.template_residual == event.prompt_tokens - sum(getattr(components, k) for k in BLOCKS), "Incorrect template residual")
            used = response["memory_used"]
            require(used["policy"] == spec.policy and used["short_term_count"] == len(used["short_term_messages"]) <= spec.n,
                    "Window or policy mismatch")
            require(texts.window == render_window(used["short_term_messages"]), "Selected window text mismatch")
            require(request["message"] in texts.current_message, "Current-message component mismatch")
            if spec.id == "D":
                require(components.window <= 160, "Eviction budget exceeded")
            if count_tokens:
                require(all(getattr(components, k) == (count_tokens(getattr(texts, k)) if getattr(texts, k) else 0)
                            for k in BLOCKS), "Component estimates differ from injected tokenizer")
            operations = [e.operation for e in correlated]
            require(operations.count("query") == operations.count("extraction") == 1, "Missing/duplicate auxiliary work")
            if index < 30 and (index + 1) % cfg["summarize_every_user_msgs"] == 0:
                require(operations.count("session_summary") == 1, "Scheduled summary event missing")
            results.append(dict(client=row, main=event, auxiliary=[e for e in correlated if e.kind == "generation"],
                                embeddings=[e for e in correlated if e.kind == "embedding"]))
        joined[spec.id] = results
    return manifest, probes, joined
