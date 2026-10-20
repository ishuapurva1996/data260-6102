"""Live HTTPS boundary. Invoked only after the later user measurement prompt."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from time import monotonic, sleep

import httpx

from scripts.hw06.runtime_lease import RuntimeLease
from src.hw06_shared.config import HW6Config
from .design import ROOT, digest, file_hash, load_design
from .runner import RequestFailed, StudyRunner, write_json
from .validation import require

SOURCE_PATHS = ("src", "code/web_application", "scripts", "tests", "memory_probes.yaml",
                "requirements-hw06.txt", "requirements-hw06.lock.txt", "AGENT.md", "MEMORY.md")
RUNTIME_ROOT = Path("/Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime")


def source_state(root: Path = ROOT):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    require(not git("status", "--porcelain", "--", *SOURCE_PATHS), "Commit source/configuration before measuring")
    files = git("ls-files", "--", *SOURCE_PATHS).splitlines()
    hashes = {name: file_hash(root / name) for name in files if (root / name).is_file()}
    return dict(source_commit=git("rev-parse", "HEAD"), source_sha256=digest(hashes), source_hashes=hashes,
                lock_sha256=file_hash(root / "requirements-hw06.lock.txt"))


def verify_gate(path: Path, config: HW6Config, state: dict, hashes: dict):
    gate = json.loads(Path(path).read_text())
    require(gate.get("live_integrated_ready") is True, "A has not published live integrated readiness")
    require(all(gate.get(key) == state[key] for key in ("source_commit", "source_sha256")), "Gate source does not match checkout")
    require(gate.get("input_hashes") == hashes, "Gate input freeze differs")
    require(gate.get("config_sha256") == digest(config.public_dict()), "Gate configuration differs")
    require(gate.get("file_memory_enabled") is False, "Gate must establish file memory is disabled")
    pilot = gate.get("pilot", {})
    require(pilot.get("n30_context_fit") is True and pilot.get("no_prompt_truncation") is True,
            "A must complete an unscored N30 context-fit pilot before measurement")
    return gate


def verify_model_identities(payload: dict, config: HW6Config):
    installed = {m["name"]: m["digest"] for m in payload.get("models", [])}
    for name, expected in ((config.model, config.model_digest), (config.embedding_model, config.embedding_digest)):
        require(bool(expected) and installed.get(name) == expected, "Installed model digest differs from frozen configuration")


class HttpEndpoint:
    def __init__(self, client: httpx.Client):
        self.client = client

    def configuration(self):
        response = self.client.get("/api/hw06/config")
        response.raise_for_status()
        payload = response.json()
        if "config" in payload:
            require(payload.get("source_commit", payload["config"].get("source_commit")) == payload["config"].get("source_commit"),
                    "Server revision metadata disagrees")
            return payload["config"]
        return payload

    def chat(self, request, context):
        headers = {"X-HW6-" + key.replace("_", "-"): str(value)
                   for key, value in context.model_dump().items()
                   if key != "source_commit" and value is not None}
        try:
            response = self.client.post("/api/chat", json=request.model_dump(), headers=headers)
        except httpx.HTTPError as exc:
            raise RequestFailed(None, {"transport_error": type(exc).__name__}, "http_transport_error") from None
        try:
            payload = response.json()
        except ValueError:
            # Preserve non-JSON server responses as real failure evidence too.
            raise RequestFailed(response.status_code, {"body": response.text}, "non_json_response") from None
        if response.status_code != 200:
            code = payload.get("code", f"http_{response.status_code}") if isinstance(payload, dict) else f"http_{response.status_code}"
            raise RequestFailed(response.status_code, payload, code)
        return payload


def port_in_use():
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", 8702)) == 0


class LiveFactory:
    """One freshly configured integrated app process per condition, no hot mutation."""
    def __init__(self, *, env_files, cert, key, ca, runtime_dir, lease, owner_id, email, password, root=ROOT):
        self.env_files, self.cert, self.key, self.ca = env_files, cert, key, ca
        self.runtime_dir, self.lease, self.owner_id = runtime_dir, lease, str(owner_id)
        self.email, self.password, self.root = email, password, root

    @contextmanager
    def __call__(self, config, directory):
        require(not port_in_use(), "Port 8702 already has an owner; do not stop it")
        require(bool(self.lease.token), "Parent must hold runtime lease")
        config_path = directory / "launch_config.json"
        write_json(config_path, config.public_dict())
        command = [sys.executable, "-B", "-m", "scripts.hw06.part3.serve",
                   "--config-json", str(config_path), "--events", str(directory / "events.jsonl"),
                   "--runtime-dir", str(self.runtime_dir), "--cert", str(self.cert), "--key", str(self.key)]
        for path in self.env_files:
            command.extend(["--env-file", str(path)])
        child_env = {**os.environ, "PYTHONPATH": str(self.root) + os.pathsep + str(self.root / "code"),
                     "PYTHONDONTWRITEBYTECODE": "1", "HW6_D_LEASE_TOKEN": self.lease.token}
        log_path = directory / "server.log"
        with log_path.open("x") as log:
            log_path.chmod(0o600)
            process = subprocess.Popen(command, cwd=self.root, env=child_env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = monotonic() + 30
                while not port_in_use():
                    require(process.poll() is None, "Owned app failed to start; inspect server.log")
                    require(monotonic() < deadline, "Owned app startup timed out")
                    sleep(0.1)
                tls = ssl.create_default_context(cafile=str(self.ca))
                with httpx.Client(base_url="https://127.0.0.1:8702", verify=tls,
                                  timeout=config.model_timeout * 12, trust_env=False) as client:
                    response = client.post("/api/auth/login", json={"email": self.email, "password": self.password})
                    require(response.status_code == 200, "Real HTTPS login failed")
                    require(str(response.json()["user"]["id"]) == self.owner_id, "Authenticated owner differs from namespace")
                    # Cookie/password/login response are deliberately not written to evidence.
                    yield HttpEndpoint(client)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()  # exclusively the subprocess created above
                        process.wait(timeout=10)


def run_live(*, gate_path, output, runtime_dir, env_files, cert, key, ca, owner_id, email, password):
    """Caller has explicit later measurement authorization; CLI enforces its flag."""
    from dotenv import load_dotenv
    require(Path(runtime_dir).resolve() == RUNTIME_ROOT, "Use A's one shared runtime lease directory")
    for path in env_files:
        load_dotenv(path, override=True)
    state = source_state()
    base = HW6Config.from_env()
    config = HW6Config(**{**base.model_dump(), "source_commit": state["source_commit"],
                           "short_term_n": 12, "policy": "baseline", "token_budget": 160})
    _, _, hashes = load_design()
    gate = verify_gate(gate_path, config, state, hashes)
    with RuntimeLease(runtime_dir, owner="D", purpose="full Part 3 measurement window") as lease:
        require(not port_in_use(), "Port 8702 already has an owner")
        with httpx.Client(base_url=config.ollama_url, timeout=10, trust_env=False) as models:
            before = models.get("/api/tags")
            before.raise_for_status()
            verify_model_identities(before.json(), config)
        factory = LiveFactory(env_files=env_files, cert=cert, key=key, ca=ca, runtime_dir=runtime_dir,
                              lease=lease, owner_id=owner_id, email=email, password=password)
        provenance = dict(**state, gate_sha256=file_hash(Path(gate_path)), gate=gate,
                          installed_models=before.json(), runtime_dir=str(Path(runtime_dir).resolve()),
                          policy_factory="src.hw06_experiments.policy.token_budget_window")
        manifest = StudyRunner(base_config=config, owner_id=str(owner_id), endpoint_factory=factory,
                               output=Path(output), evidence_kind="measured_http").run(provenance=provenance)
        try:
            require(source_state() == state and load_design()[2] == hashes, "Source or input changed during measurement")
            with httpx.Client(base_url=config.ollama_url, timeout=10, trust_env=False) as models:
                after = models.get("/api/tags")
                after.raise_for_status()
                verify_model_identities(after.json(), config)
            write_json(Path(output) / "postflight.json", dict(source_unchanged=True, installed_models=after.json()))
        except BaseException as exc:
            manifest.update(status="incomplete", failure=dict(type=type(exc).__name__, code="postflight_failed"))
            write_json(Path(output) / "manifest.json", manifest)
            raise
    return manifest
