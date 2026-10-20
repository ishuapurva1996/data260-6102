"""Factory integration; real model/database acceptance is a separate command."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.hw06_shared.config import HW6Config
from src.hw06_shared.telemetry import NullTelemetry
from web_application.main import create_app
from web_application.routers.auth import require_user


def test_existing_factory_stays_usable_without_hw6_runtime():
    with TestClient(create_app()) as client:
        assert client.get('/api/health').status_code == 200
        schema = client.get('/openapi.json').json()
        assert '/api/property-managers' in schema['paths']
        assert '/api/chat' not in schema['paths']


def test_factory_mounts_shared_services_and_enforces_existing_auth(monkeypatch):
    import src.hw06_shared.runtime as runtime
    seen = {}
    database = object()
    connection = SimpleNamespace(database=database, close=lambda: seen.update(closed=True))
    def documents(db):
        seen['documents_db'] = db
        return SimpleNamespace(list=lambda: [])
    def storage(db):
        seen['memory_db'] = db
        return SimpleNamespace(database=db)
    def memory(**kwargs):
        seen['memory_dependencies'] = kwargs
        return SimpleNamespace(config=kwargs['config'])
    monkeypatch.setattr(runtime, 'DocumentService', documents)
    monkeypatch.setattr(runtime, 'MongoMemoryStorage', storage)
    monkeypatch.setattr(runtime, 'MongoMemoryService', memory)
    config = HW6Config(policy='token_budget')
    app = create_app(hw6_config=config, hw6_connection=connection,
                     hw6_model=object(), hw6_embedder=lambda text: [1.0],
                     hw6_count_tokens=len, hw6_telemetry=NullTelemetry())
    assert seen['documents_db'] is seen['memory_db'] is database
    assert seen['memory_dependencies']['window_policy'] is not None
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=1)
    with TestClient(app) as client:
        assert client.get('/api/doc-rentals').json() == []
        actual = client.get('/api/hw06/config').json()
        assert actual['config']['policy'] == 'token_budget'
        assert 'mongo_uri' not in actual['config']
        assert actual['file_memory_enabled'] is False
        assert actual['source_commit'] == actual['config']['source_commit']
        paths = client.get('/openapi.json').json()['paths']
        assert {'/api/chat','/api/memory/{user_id}','/api/aggregate/{user_id}'} <= paths.keys()
    assert seen['closed']
