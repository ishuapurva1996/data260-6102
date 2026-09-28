"""Database cleanup failure must not strand an owned HTTPS server."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('hw4_acceptance',Path(__file__).resolve().parents[1]/'scripts/hw04/part2/acceptance.py')
acceptance=importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def test_failed_database_cleanup_still_stops_server_and_closes_resources():
    events=[]
    def fail_db():
        raise RuntimeError('private details must not enter report')
    engine=SimpleNamespace(begin=fail_db,dispose=lambda:events.append('dispose'))
    client=SimpleNamespace(close=lambda:events.append('client'))
    failures=acceptance.cleanup_owned_resources(engine,13,None,lambda:events.append('stop'),client)
    assert events==['stop','client','dispose']
    assert failures==[{'resource':'database test rows','error_type':'RuntimeError'}]


def test_no_test_rows_avoids_database_cleanup_connection():
    events=[]
    def unexpected_db():
        raise AssertionError('No rows were created')
    engine=SimpleNamespace(begin=unexpected_db,dispose=lambda:events.append('dispose'))
    assert acceptance.cleanup_owned_resources(engine,None,None,lambda:events.append('stop'),
                                              SimpleNamespace(close=lambda:events.append('client')))==[]
    assert events==['stop','client','dispose']
