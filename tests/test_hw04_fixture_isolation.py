"""Root fixture discovery must work in the separate retrieval environment."""
import builtins
import importlib.util
from pathlib import Path


def test_root_conftest_does_not_import_web_stack_until_fixtures_run(monkeypatch):
    original=builtins.__import__
    def without_web(name,*args,**kwargs):
        if name.split('.')[0] in {'fastapi','sqlalchemy','argon2','web_application'}:
            raise ImportError('Web stack intentionally unavailable')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',without_web)
    path=Path(__file__).with_name('conftest.py')
    spec=importlib.util.spec_from_file_location('isolated_fixture_collection',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.hw4_engine)
