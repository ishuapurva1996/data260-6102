"""Run only after a later measurement prompt and A's integrated gate."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurement-authorized", action="store_true")
    for option in ("gate", "output", "runtime-dir", "cert", "key", "ca"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--env-file", type=Path, action="append", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--email-env", default="HW6_EXPERIMENT_EMAIL")
    parser.add_argument("--password-env", default="HW6_EXPERIMENT_PASSWORD")
    args = parser.parse_args()
    if not args.measurement_authorized:
        parser.error("Requires the later user measurement prompt; preparation must not run live comparisons")
    from dotenv import load_dotenv
    for path in args.env_file:
        load_dotenv(path, override=True)
    if not os.environ.get(args.email_env) or not os.environ.get(args.password_env):
        parser.error("Set login credentials in private environment variables")
    from src.hw06_experiments.live import run_live
    run_live(gate_path=args.gate, output=args.output, runtime_dir=args.runtime_dir, env_files=args.env_file,
             cert=args.cert, key=args.key, ca=args.ca, owner_id=args.owner_id,
             email=os.environ[args.email_env], password=os.environ[args.password_env])
    print("Collected 120 primary and 20 probe requests; validate events and manually score before export.")


if __name__ == "__main__":
    main()
