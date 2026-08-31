#!/usr/bin/env python3
"""Two-agent Ollama pipeline for DATA 260 Homework 1, Part 2.

The Planner proposes tags and a summary. The Reviewer receives that proposal and
may correct it. A deterministic finalization step then validates the schema before
the publish package is printed. Domain information is supplied only through the
command-line title and content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.model_client import build_ollama_client


STOP = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "into",
    "than",
    "your",
    "you",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "use",
    "used",
    "using",
    "about",
    "how",
    "can",
    "will",
    "more",
    "less",
    "very",
    "over",
    "under",
    "their",
    "there",
    "then",
    "our",
    "out",
    "on",
    "in",
    "of",
    "to",
    "by",
    "a",
    "an",
    "is",
    "it",
    "as",
}


def strip_code_and_md(value: Any) -> str:
    """Remove common Markdown artifacts and normalize whitespace."""

    text = str(value or "")
    text = re.sub(r"```(?:json|javascript|python|text)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").replace("`", "")
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+|>\s*)", "", text)
    return " ".join(text.split())


def extract_json_block(text: Any) -> str:
    """Return the first valid JSON object found in a model response."""

    raw = str(text or "").strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(raw):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return json.dumps(parsed, ensure_ascii=False)
    return json.dumps({"message": strip_code_and_md(raw)}, ensure_ascii=False)


def tokens(text: Any) -> List[str]:
    """Tokenize text into lowercase words while retaining internal hyphens."""

    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(text or "").lower())


def ngrams(words: Sequence[str], n: int) -> Iterable[Tuple[str, ...]]:
    """Yield all contiguous n-grams in order."""

    if n <= 0:
        return
    for index in range(max(0, len(words) - n + 1)):
        yield tuple(words[index : index + n])


def phrase_candidates(title: str, content: str, maxn: int = 12) -> List[str]:
    """Build ranked tag candidates using only words from title and content."""

    if maxn <= 0:
        return []
    source_words = [word for word in tokens(f"{title} {content}") if word not in STOP]
    if not source_words:
        return []

    ranked: List[str] = []
    seen = set()

    for size in (3, 2):
        for phrase, _ in Counter(ngrams(source_words, size)).most_common():
            candidate = " ".join(phrase)
            if candidate not in seen:
                seen.add(candidate)
                ranked.append(candidate)

    for word, _ in Counter(source_words).most_common():
        if word not in seen:
            seen.add(word)
            ranked.append(word)

    return ranked[:maxn]


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    return " ".join(words[:limit])


def _normalize_tag(value: Any) -> str:
    tag = strip_code_and_md(value).strip(" .,:;!?\"'").lower()
    return _truncate_words(tag, 5)


def _is_topical(tag: str, source: set[str]) -> bool:
    tag_words = {word for word in tokens(tag) if word not in STOP}
    return bool(tag_words and tag_words.issubset(source))


def _final_tags(raw_tags: Any, title: str, content: str) -> List[str]:
    supplied = raw_tags if isinstance(raw_tags, list) else []
    source_tokens = [word for word in tokens(f"{title} {content}") if word not in STOP]
    source = set(source_tokens)
    candidates = phrase_candidates(title, content, maxn=24)
    result: List[str] = []

    def add(value: Any) -> None:
        tag = _normalize_tag(value)
        if tag and tag not in result and _is_topical(tag, source):
            result.append(tag)

    for tag in supplied:
        add(tag)
    for candidate in candidates:
        if len(result) >= 3:
            break
        add(candidate)

    if sum(" " in tag for tag in result[:3]) < 2:
        multiword = [candidate for candidate in candidates if " " in candidate]
        for candidate in multiword:
            if candidate in result[:3]:
                continue
            replace_at = next(
                (index for index, tag in reversed(list(enumerate(result[:3]))) if " " not in tag),
                None,
            )
            if replace_at is None:
                break
            result[replace_at] = candidate
            if sum(" " in tag for tag in result[:3]) >= 2:
                break

    if len(result) < 3:
        raise ValueError(
            "The title and content do not contain enough distinct topical phrases "
            "to produce exactly three input-derived tags."
        )
    return result[:3]


def _summary_is_grounded(summary: str, title: str, content: str) -> bool:
    """Require most meaningful summary terms to occur in the supplied input."""

    summary_terms = [word for word in tokens(summary) if word not in STOP]
    source_terms = set(tokens(f"{title} {content}"))
    if not summary_terms:
        return False
    supported = sum(word in source_terms for word in summary_terms)
    return supported * 2 >= len(summary_terms)


def _final_summary(raw_summary: Any, title: str, content: str) -> str:
    summary = strip_code_and_md(raw_summary)
    sentence = re.match(r"^(.+?[.!?])(?:\s|$)", summary)
    if sentence:
        summary = sentence.group(1)
    if not summary or not _summary_is_grounded(summary, title, content):
        summary = strip_code_and_md(content)
        sentence = re.match(r"^(.+?[.!?])(?:\s|$)", summary)
        if sentence:
            summary = sentence.group(1)
    summary = _truncate_words(summary, 25).rstrip(" .,:;!?…")
    return f"{summary}." if summary else "Summary unavailable."


def _validate_input(title: str, content: str) -> None:
    """Reject input that cannot support input-derived metadata."""

    if len(phrase_candidates(title, content, maxn=3)) < 3:
        raise ValueError(
            "Title and content must include enough meaningful terms to produce "
            "exactly three input-derived tags."
        )


def coerce_reply(
    raw_obj: Any,
    title: str,
    content: str,
) -> Dict[str, Any]:
    """Coerce arbitrary model output into the assignment's strict schema."""

    obj = raw_obj if isinstance(raw_obj, dict) else {"message": str(raw_obj or "")}
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}

    thought = _truncate_words(strip_code_and_md(obj.get("thought", "")), 60)
    message = _truncate_words(strip_code_and_md(obj.get("message", "")), 60)
    copied_placeholders = {
        "non-empty status under 60 words",
        "short completion status",
    }
    if not message or message.lower().strip(" .") in copied_placeholders:
        message = "Proposal reviewed; tags and summary are ready."

    raw_summary = strip_code_and_md(data.get("summary", ""))
    final_tags = _final_tags(data.get("tags", []), title, content)
    final_summary = _final_summary(raw_summary, title, content)

    issues_value = data.get("issues", [])
    if isinstance(issues_value, list):
        issues = []
        for issue in issues_value:
            cleaned = strip_code_and_md(issue)
            if cleaned:
                issues.append(cleaned)
    else:
        cleaned = strip_code_and_md(issues_value)
        issues = [cleaned] if cleaned else []

    validated_issues = []
    tags_are_distinct = len(final_tags) == 3 and len(set(final_tags)) == 3
    summary_is_short = bool(raw_summary) and len(raw_summary.split()) <= 25
    for issue in issues:
        lowered = issue.lower()
        false_summary_issue = (
            summary_is_short
            and "summary" in lowered
            and any(term in lowered for term in ("25", "long", "exceed"))
        )
        false_tag_issue = (
            tags_are_distinct
            and "tag" in lowered
            and any(term in lowered for term in ("overlap", "duplicate", "exactly three"))
        )
        if not false_summary_issue and not false_tag_issue:
            validated_issues.append(issue)

    return {
        "thought": thought,
        "message": message,
        "data": {
            "tags": final_tags,
            "summary": final_summary,
            "issues": validated_issues,
        },
    }


def parse_and_coerce(
    text: Any,
    title: str,
    content: str,
) -> Dict[str, Any]:
    """Parse a response as JSON and always return a valid assignment schema."""

    return coerce_reply(parse_reply(text), title, content)


def parse_reply(text: Any) -> Dict[str, Any]:
    """Parse a model response without repairing or normalizing its content."""

    try:
        parsed = json.loads(extract_json_block(text))
    except (TypeError, json.JSONDecodeError):
        parsed = {"message": str(text or "")}
    return parsed if isinstance(parsed, dict) else {"message": str(text or "")}


def parse_strict_agent_reply(text: Any) -> Dict[str, Any]:
    """Validate that an agent returned exactly one complete JSON object."""

    raw = str(text or "").strip()
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Agent response must be exactly one valid JSON object") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Agent response must be a JSON object")
    if not isinstance(parsed.get("thought"), str) or not isinstance(
        parsed.get("message"), str
    ):
        raise ValueError("Agent response requires string thought and message fields")

    data = parsed.get("data")
    if not isinstance(data, dict):
        raise ValueError("Agent response requires a data object")
    if not isinstance(data.get("tags"), list) or not all(
        isinstance(tag, str) for tag in data["tags"]
    ):
        raise ValueError("Agent response data.tags must be an array of strings")
    if not isinstance(data.get("summary"), str):
        raise ValueError("Agent response data.summary must be a string")
    if not isinstance(data.get("issues"), list) or not all(
        isinstance(issue, str) for issue in data["issues"]
    ):
        raise ValueError("Agent response data.issues must be an array of strings")
    return parsed


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                pieces.append(item["text"])
            else:
                pieces.append(str(item))
        return "".join(pieces)
    return str(content)


class SimpleAgent:
    """Small wrapper around the shared model-client interface."""

    def __init__(self, system: str, model: Any) -> None:
        self.system = system
        self.model = model

    def respond(
        self,
        conversation: List[Dict[str, Any]],
        task: str,
        title: str,
        content: str,
    ) -> Tuple[Dict[str, Any], str]:
        history_text = json.dumps(conversation, ensure_ascii=False, indent=2)
        human_prompt = (
            f"Task and input:\n{task}\n\n"
            f"Conversation so far:\n{history_text}\n\n"
            "Return ONLY one JSON object containing string keys thought and message, plus "
            "a data object containing tags, summary, and issues. "
            "Use exactly three distinct topical tags derived from the supplied title/content. "
            "Keep thought brief, message under 60 words, summary to one sentence of at most "
            "25 words, and issues as an array. "
            "Do not use Markdown, code fences, or text outside the JSON object."
        )
        response = self.model.complete(
            [
                ("system", self.system),
                ("human", human_prompt),
            ]
        )
        raw_response = _response_text(response)
        return parse_strict_agent_reply(raw_response), raw_response


def finalize_reply(
    reviewer_reply: Dict[str, Any],
    title: str,
    content: str,
) -> Dict[str, Any]:
    """Normalize, validate, and package the Reviewer's raw proposal."""

    reviewed_reply = coerce_reply(reviewer_reply, title, content)
    reviewed = reviewed_reply["data"]
    if reviewed["issues"]:
        raise ValueError(
            "Reviewer reported unresolved issues; refusing to create publish output: "
            + "; ".join(reviewed["issues"])
        )
    return {
        "thought": "Reviewer proposal selected and schema validated.",
        "message": "Final tags and summary are ready for publishing.",
        "data": {
            "tags": reviewed["tags"],
            "summary": reviewed["summary"],
            "issues": [],
        },
    }


def run_pipeline(
    model: Any,
    title: str,
    content: str,
    email: str,
) -> Dict[str, Any]:
    """Run Planner, Reviewer, and deterministic Finalizer steps."""

    _validate_input(title, content)
    input_payload = {"title": title, "content": content}
    task = (
        "Create exactly three topical tags and a one-sentence summary of at most "
        f"25 words for this input: {json.dumps(input_payload, ensure_ascii=False)}"
    )
    transcript: List[Dict[str, Any]] = []

    planner = SimpleAgent(
        system=(
            "You are the Planner. Propose exactly three distinct topical tags, preferring "
            "specific multi-word phrases, and one faithful sentence summarizing only the input."
        ),
        model=model,
    )
    reviewer = SimpleAgent(
        system=(
            "You are the Reviewer. Inspect the Planner proposal in the conversation. Correct "
            "generic, duplicated, unsupported, or poorly phrased tags; ensure the summary is "
            "faithful, one sentence, and no more than 25 words. Return the cleaned proposal."
        ),
        model=model,
    )

    started = time.perf_counter()
    planner_reply, planner_raw = planner.respond(transcript, task, title, content)
    planner_ms = round((time.perf_counter() - started) * 1000)
    transcript.append({"role": "Planner", "content": planner_reply})

    started = time.perf_counter()
    reviewer_history = [{"role": "Planner", "content": planner_raw}]
    reviewer_reply, _ = reviewer.respond(reviewer_history, task, title, content)
    reviewer_ms = round((time.perf_counter() - started) * 1000)
    transcript.append({"role": "Reviewer", "content": reviewer_reply})

    finalized = finalize_reply(reviewer_reply, title, content)
    reviewer_changed = planner_reply.get("data") != reviewer_reply.get("data")
    package = {
        "title": title,
        "email": email,
        "content": content,
        "agents": {
            "transcript": transcript,
            "reviewerChanged": reviewer_changed,
            "final": finalized["data"],
        },
        "submissionDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return {
        "planner": planner_reply,
        "reviewer": reviewer_reply,
        "finalized": finalized,
        "reviewer_changed": reviewer_changed,
        "latency_ms": {"planner": planner_ms, "reviewer": reviewer_ms},
        "package": package,
    }


def create_model(
    model_name: str,
    base_url: str,
    temperature: float,
    timeout: float,
) -> Any:
    """Create the shared Ollama adapter in strict-JSON mode."""

    return build_ollama_client(
        model_name,
        base_url,
        temperature,
        timeout,
        response_format="json",
        reasoning=False,
    )


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the DATA 260 Part 2 Planner-Reviewer-Finalizer pipeline."
    )
    parser.add_argument("--title", required=True, help="Domain-entity title")
    parser.add_argument("--content", required=True, help="Domain-entity content")
    parser.add_argument("--email", default="student@example.com")
    parser.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:8b"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=120.0,
        help="Ollama request timeout in seconds (default: 120)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        print(
            "Error: this assignment requires Python 3.11 or 3.12; "
            f"current interpreter is {sys.version.split()[0]}.",
            file=sys.stderr,
        )
        return 2

    try:
        model = create_model(args.model, args.base_url, args.temperature, args.timeout)
        result = run_pipeline(model, args.title, args.content, args.email)
    except Exception as exc:
        print(
            f"Agent pipeline failed: {exc}\n"
            "Confirm that Ollama is running and the requested model is installed "
            f"(`ollama pull {args.model}`).",
            file=sys.stderr,
        )
        return 1

    print(f"\n--- Planner ({result['latency_ms']['planner']} ms) ---")
    print(json.dumps(result["planner"], indent=2, ensure_ascii=False))
    print(f"\n--- Reviewer ({result['latency_ms']['reviewer']} ms) ---")
    print(json.dumps(result["reviewer"], indent=2, ensure_ascii=False))
    print("\n--- Finalized Output ---")
    print(json.dumps(result["finalized"], indent=2, ensure_ascii=False))
    print("\n--- Publish Output ---")
    print(json.dumps(result["package"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
