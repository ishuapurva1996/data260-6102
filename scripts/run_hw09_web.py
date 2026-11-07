"""Run the integrated HW9 app on the assigned port with version enforcement."""

import logging
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]


def main():
    os.environ["HW8_KAFKA_ENABLED"] = "1"
    os.environ["HW9_CACHE_ENABLED"] = "1"
    os.environ["HW9_CACHE_DEMO_ALLOW_STALE"] = "0"
    os.environ.setdefault("HW9_CACHE_THRESHOLD", "0.85")
    os.environ.setdefault("HW9_CACHE_NAMESPACE", "integration")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run("web_application.main:app", host="127.0.0.1", port=8702, workers=1)


if __name__ == "__main__":
    main()
