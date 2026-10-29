"""HW8 reviewer process entry point."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.kafka_agents.common import main

if __name__ == "__main__":
    main("reviewer")
