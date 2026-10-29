"""Fixed semester identity and the seven explicitly provisioned HW8 topics."""
from dataclasses import dataclass
import os

SID4 = SEED = 6102
PORT_BASE = 8702
PREFIX = 's6102'
VERIFY_SEED = 266102
DOMAIN_ID = 6
ENTITY_REQUESTS = f'{PREFIX}_entity_requests'
ENTITY_RESPONSES = f'{PREFIX}_entity_responses'
INBOX = f'{PREFIX}_inbox'
TASKS = f'{PREFIX}_tasks'
DRAFTS = f'{PREFIX}_drafts'
FINAL = f'{PREFIX}_final'
DEAD_LETTER = f'{PREFIX}_dead_letter'
TOPICS = {ENTITY_REQUESTS: 1, ENTITY_RESPONSES: 1, INBOX: 1, TASKS: 2,
          DRAFTS: 1, FINAL: 1, DEAD_LETTER: 1}

@dataclass(frozen=True)
class KafkaSettings:
    bootstrap_servers: str = '127.0.0.1:9092'
    rpc_timeout: float = 8.0
    assignment_timeout: float = 30.0

    @classmethod
    def from_env(cls):
        return cls(bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', '127.0.0.1:9092'),
                   rpc_timeout=float(os.getenv('HW8_RPC_TIMEOUT', '8')),
                   assignment_timeout=float(os.getenv('HW8_ASSIGNMENT_TIMEOUT', '30')))
