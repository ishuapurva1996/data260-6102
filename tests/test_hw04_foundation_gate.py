"""Regression gate replacing the old public rental API."""
import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

def test_rental_access_requires_login():
    path = Path(__file__).resolve().parents[1] / "code/web_application/main.py"
    spec = importlib.util.spec_from_file_location("hw4_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.create_app(), base_url="https://testserver") as client:
        response = client.get("/api/rentals")
        assert response.status_code == 401
        assert isinstance(response.json()["detail"], str)
