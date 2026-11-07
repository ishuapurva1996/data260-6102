"""Submit one question and read its correlated final result through Kafka."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.kafka_agents.question_client import send_question


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question",
        nargs="?",
        default="How does Kafka message ordering affect updates to the same rental listing?",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--correlation-id")
    parser.add_argument("--rental-id")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        send_question(
            args.question,
            run_id=args.run_id,
            correlation_id=args.correlation_id,
            timeout=args.timeout,
            rental_id=args.rental_id,
        )
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["final"], indent=2))


if __name__ == "__main__":
    main()
