"""Factory ownership, wrapping, and no-I/O construction contract."""
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
