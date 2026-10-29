"""HTTP launcher for the existing semester app; previous TLS launchers are retained."""

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]
from src.kafka_service.logging import event


def main():
    event("web_host_url", url="http://127.0.0.1:8702", bind="0.0.0.0:8702")
    uvicorn.run("web_application.main:app", host="0.0.0.0", port=8702, workers=1)


if __name__ == "__main__":
    main()
