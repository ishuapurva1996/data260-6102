"""Factory ownership, wrapping, and no-I/O construction contract."""
import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.rental_tools.runtime import build_service
from src.rental_tools.reliability import RetryPolicy, RetryingRentalReader


class FalseyReader:
    def __bool__(self):
        return False
    def get_rental(self, rental_id):
        return None


def test_falsey_injected_reader_and_optional_close():
    inner = FalseyReader()
    service = build_service(reader=inner)
    assert isinstance(service.reader, RetryingRentalReader)
    assert service.reader.reader is inner
    assert service.get_rental(rental_id=8)["error"] == "Rental 8 was not found."
    service.reader.close()
    service.reader.close()


def test_wrapped_reader_reused_and_conflicts_rejected():
    observer = lambda event: None
    reader = RetryingRentalReader(FalseyReader(), attempt_observer=observer)
    assert build_service(reader=reader).reader is reader
    assert build_service(reader=reader, policy=RetryPolicy(), attempt_observer=observer).reader is reader
    with pytest.raises(ValueError):
        build_service(reader=reader, policy=RetryPolicy(max_attempts=1))
    with pytest.raises(ValueError):
        build_service(reader=reader, attempt_observer=lambda event: None)
    with pytest.raises(ValueError):
        RetryingRentalReader(reader)


def test_import_and_factory_do_not_read_secret_environment_or_connect():
    code = '''
import os, socket, sqlalchemy
def blocked(*args, **kwargs):
    raise AssertionError('Construction attempted I/O')
socket.socket.connect = blocked
socket.create_connection = blocked
sqlalchemy.create_engine = blocked
original = os.environ.get
def guard(key, *args):
    if key == 'HW5_MCP_DATABASE_URL':
        raise AssertionError('Secret environment inspected')
    return original(key, *args)
os.environ.get = guard
from src.rental_tools.runtime import build_service
from src.mcp_servers.rentals import create_server
service = build_service()
create_server()
service.reader.close()
'''
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("flags,optimize", [(["-O"], None), (["-OO"], None), ([], "1"), ([], "2")])
def test_live_capture_rejects_optimization_before_environment_or_stdio(tmp_path, flags, optimize):
    """Real optimized interpreters must fail closed before any capture side effect."""
    output = tmp_path / "receipt.json"
    accessed = tmp_path / "capture-access.txt"
    code = '''
from pathlib import Path
from types import SimpleNamespace
import sys
import scripts.hw05.part3.capture_live_stdio as capture_module

destination, marker = sys.argv[1:]

class ForbiddenEnvironment:
    def __getitem__(self, key):
        Path(marker).write_text('environment accessed')
        raise RuntimeError('PRIVATE_SENTINEL')

def forbidden_stdio(*args, **kwargs):
    Path(marker).write_text('STDIO started')
    raise RuntimeError('PRIVATE_SENTINEL')

capture_module.os = SimpleNamespace(environ=ForbiddenEnvironment())
capture_module.stdio_client = forbidden_stdio
sys.argv = ['capture_live_stdio.py', destination]
raise SystemExit(capture_module.main())
'''
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONOPTIMIZE", "HW5_MCP_DATABASE_URL"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if optimize is not None:
        env["PYTHONOPTIMIZE"] = optimize
    result = subprocess.run([sys.executable, *flags, "-c", code, str(output), str(accessed)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "Live STDIO verification failed; no passing receipt produced.\n"
    assert not output.exists()
    assert not accessed.exists(), "Disabled assertions must be rejected before environment/STDIO access"


@pytest.mark.parametrize("failure", ["empty_inventory", "transport_error"])
def test_live_capture_normal_mode_rejects_failing_responses(tmp_path, failure):
    """Protocol doubles test verifier failures; they are not live MySQL proof."""
    output = tmp_path / "receipt.json"
    observed = tmp_path / "observed.txt"
    code = '''
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import scripts.hw05.part3.capture_live_stdio as capture_module

destination, observation, failure = sys.argv[1:]
os.environ['HW5_MCP_DATABASE_URL'] = 'mysql+pymysql://hw5_part3_reader:unused@127.0.0.1:3310/s6102_rel'

@asynccontextmanager
async def fake_stdio(*args, **kwargs):
    yield None, None

class FakeSession:
    def __init__(self, *args):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def initialize(self):
        return SimpleNamespace(model_dump=lambda **kwargs: {})
    async def list_tools(self):
        Path(observation).write_text('list_tools')
        tools = [] if failure == 'empty_inventory' else [
            SimpleNamespace(name=name, inputSchema=definition.input_model.model_json_schema())
            for name, definition in capture_module.TOOL_REGISTRY.items()]
        return SimpleNamespace(tools=tools, model_dump=lambda **kwargs: {})
    async def call_tool(self, *args):
        Path(observation).write_text('call_tool')
        return SimpleNamespace(isError=True, structuredContent=None,
                               model_dump=lambda **kwargs: {'isError': True, 'structuredContent': None})

capture_module.stdio_client = fake_stdio
capture_module.ClientSession = FakeSession
sys.argv = ['capture_live_stdio.py', destination]
raise SystemExit(capture_module.main())
'''
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONOPTIMIZE", "HW5_MCP_DATABASE_URL"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-c", code, str(output), str(observed), failure],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "Live STDIO verification failed; no passing receipt produced.\n"
    assert not output.exists()
    assert observed.read_text() == ("list_tools" if failure == "empty_inventory" else "call_tool")
