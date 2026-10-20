#!/usr/bin/env python3
"""Standalone file-memory CLI. JSON results on stdout; one file per user/workspace."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from scripts.hw06.runtime_lease import RuntimeLease, LeaseBusy
from src.hw06_shared.config import HW6Config
from src.hw06_shared.models import build_generation_client
from src.hw06_shared.serialization import utc_now
from src.hw06_shared.telemetry import JsonlTelemetry, RequestContext
from src.hw06_memory_files.service import FileMemoryService


class LeasedModel:
    """Acquire A's lease only for live calls; caller must not hold an outer lease."""
    def __init__(self, runtime_dir: Path, config: HW6Config):
        self.runtime_dir, self.config = runtime_dir, config
        self.client = None

    def complete(self, messages, tools=None):
        with RuntimeLease(self.runtime_dir, owner='E-file-cli', purpose='Part 4 generation'):
            if self.client is None:
                self.client = build_generation_client(self.config)
            return self.client.complete(messages, tools=tools)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-file', type=Path, default=ROOT/'AGENT.md')
    parser.add_argument('--memory-file', type=Path, default=ROOT/'MEMORY.md')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--runtime-dir', required=True, type=Path)
    parser.add_argument('--telemetry-file', type=Path)
    parser.add_argument('--message', action='append', help='Repeat for sequential inputs, or omit for stdin lines')
    args = parser.parse_args(argv)
    if args.env_file:
        load_dotenv(args.env_file)
    config = HW6Config.from_env()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    service = FileMemoryService(agent_path=args.agent_file, memory_path=args.memory_file,
                                model=LeasedModel(args.runtime_dir, config),
                                telemetry=JsonlTelemetry(args.telemetry_file) if args.telemetry_file else None)
    history = []
    failed = False
    messages = args.message if args.message else (line.rstrip('\n') for line in sys.stdin)
    for message in messages:
        if not message.strip():
            continue
        try:
            result = service.handle(message, recent_messages=history,
                                    context=RequestContext(source_commit=revision))
        except LeaseBusy:
            result = {'reply':'Shared runtime is leased; retry after its owner finishes.', 'error':'lease_busy'}
        except (OSError, ValueError, RuntimeError):
            result = {'reply':'File/model operation failed; inspect paths and runtime availability.',
                      'error':'operation_failed'}
        except Exception:
            # Never print backend exception text, which may include configuration secrets.
            result = {'reply':'Model operation failed; memory was not replaced by this call.', 'error':'model_failure'}
        print(json.dumps(result, ensure_ascii=False), flush=True)
        failed |= 'error' in result
        if result.get('kind') == 'reply' and 'error' not in result:
            for role, content in [('user', message), ('assistant', result['reply'])]:
                history.append({'id':uuid4().hex, 'role':role, 'content':content,
                                'user_id':'file-local', 'session_id':'file-local', 'created_at':utc_now()})
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
