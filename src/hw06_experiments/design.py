"""Fixed study conditions and input provenance; no model work on import."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import yaml

from src.hw06_shared.config import HW6Config

ROOT = Path(__file__).resolve().parents[2]
CONVERSATION = Path("scripts/hw06/part3/conversation.json")
PROBES = Path("memory_probes.yaml")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Condition:
    id: str
    n: int
    policy: str = "baseline"

    @property
    def label(self):
        return f"N={self.n}" + (" + token-budget eviction" if self.policy != "baseline" else "")

    def configure(self, base: HW6Config) -> HW6Config:
        return HW6Config(**{**base.model_dump(), "short_term_n": self.n,
                           "policy": self.policy, "token_budget": 160})


CONDITIONS = (Condition("A", 4), Condition("B", 12), Condition("C", 30),
              Condition("D", 12, "token_budget"))


def load_design(root: Path = ROOT):
    conversation = json.loads((root / CONVERSATION).read_text())
    probes = yaml.safe_load((root / PROBES).read_text())
    messages = conversation["messages"]
    questions = probes["probes"]
    if len(messages) != 30 or any(not isinstance(m, str) or not m.strip() for m in messages):
        raise ValueError("Exactly 30 nonblank submitted user messages are required")
    if len(questions) != 5 or [p["id"] for p in questions] != probes["probe_order"]:
        raise ValueError("Exactly five probes in frozen order are required")
    if len(set(probes["probe_order"])) != 5 or set(probes["rubric"]) != set(range(1, 6)):
        raise ValueError("Five unique probes and a 1-5 rubric are required")
    for probe in questions:
        for field in ("question", "expected_answer", "essential_criteria", "full_credit_criteria",
                      "score_4_minor_omission", "score_3_example", "provenance"):
            if not probe.get(field):
                raise ValueError(f"Missing {field} for {probe['id']}")
        for source in probe["provenance"]:
            if source["quote"] not in messages[source["turn"] - 1]:
                raise ValueError(f"Untraceable provenance for {probe['id']}")
    hashes = {str(path): file_hash(root / path) for path in (CONVERSATION, PROBES)}
    return conversation, probes, hashes
