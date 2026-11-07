"""Verify the captured Part 3 run and build its report-ready evidence bundle."""

import argparse
import base64
import hashlib
import html
import json
import shutil
from collections import Counter
from pathlib import Path

from scripts.hw09.cache_experiments import (
    DATA,
    FROZEN_COMMIT,
    FROZEN_SHA,
    load_cases,
    summarize,
    unambiguous_units,
)


def read_rows(path):
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.startswith("{")
    ]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_manifest(output):
    dump(
        output / "evidence-sha256.json",
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.iterdir())
            if p.is_file() and p.name != "evidence-sha256.json"
        },
    )


def cache_events(path):
    events = [r for r in read_rows(path) if r.get("event") == "semantic_cache_result"]
    result = {r["request_id"]: r for r in events}
    assert len(result) == len(events)
    return result


def verify_response(row, event, namespace, threshold, enforced=True):
    body = row["response"]
    assert row["status_code"] == 200 and event["error"] is None
    if "cache_event" in row:
        assert row["cache_event"] == event
    assert event["request_id"] == event["correlation_id"] == body["request_id"]
    assert event["question"] == row["question"]
    assert event["namespace"] == namespace and event["threshold"] == threshold
    assert event["version_enforced"] is enforced
    assert event["is_cached"] == body["is_cached"]
    assert event["pipeline_attempted"] != body["is_cached"]
    assert event["similarity"] == body["similarity"]
    assert event["latency_ms"] == body["latency_ms"]


def verify_demonstrations(runtime, stale, chosen):
    smoke = read_rows(runtime / "chosen-smoke.jsonl")
    assert len(stale) == 4 and len(smoke) == 2
    assert [r["response"]["is_cached"] for r in smoke] == [False, True]
    decisions = json.loads((runtime / "demonstration-audit.json").read_text())[
        "decisions"
    ]
    audits = {d["request_id"]: d for d in decisions}
    combined = [*stale, *smoke]
    assert len(decisions) == len(audits) == 6
    assert set(audits) == {r["response"]["request_id"] for r in combined}
    old_events = cache_events(runtime / "api-stale-demo-c-01-stale.log")
    fresh_events = cache_events(runtime / "api-stale-demo-c-01-enforced.log")
    smoke_events = cache_events(runtime / "api-c-chosen-smoke-01-enforced.log")
    for index, (row, units) in enumerate(zip(combined, [3, 3, 1, 1, 1, 1])):
        body = row["response"]
        request_id = body["request_id"]
        assert row["question"] == "How many units are available at S6102-R-9199?"
        events = (
            old_events if index < 2 else fresh_events if index < 4 else smoke_events
        )
        namespace = "stale-demo-c-01" if index < 4 else "c-chosen-smoke-01"
        verify_response(
            row,
            events[request_id],
            namespace,
            0.95 if index < 4 else chosen,
            index >= 2,
        )
        audit = audits[request_id]
        assert (
            audit["answer_sha256"]
            == hashlib.sha256(body["answer"].encode()).hexdigest()
        )
        assert audit["expected"] == {
            "listing_code": "S6102-R-9199",
            "field": "available_units",
            "value": units,
        }
        assert audit["correct"] is True and audit["reason"]
        assert "S6102-R-9199" in body["answer"] and unambiguous_units(
            body["answer"], units
        )
    assert (
        stale[1]["cache_event"]["matched_request_id"]
        == stale[0]["response"]["request_id"]
    )
    assert (
        stale[3]["cache_event"]["matched_request_id"]
        == stale[2]["response"]["request_id"]
    )
    assert (
        stale[0]["cache_event"]["data_version"]
        == stale[1]["cache_event"]["matched_data_version"]
    )
    assert (
        stale[1]["cache_event"]["data_version"]
        == stale[2]["cache_event"]["data_version"]
        == stale[3]["cache_event"]["data_version"]
    )
    assert stale[2]["response"]["answer"] == stale[3]["response"]["answer"]
    assert smoke[0]["response"]["answer"] == smoke[1]["response"]["answer"]
    assert (
        smoke_events[smoke[1]["response"]["request_id"]]["matched_request_id"]
        == smoke[0]["response"]["request_id"]
    )
    assert (
        smoke_events[smoke[0]["response"]["request_id"]]["data_version"]
        == smoke_events[smoke[1]["response"]["request_id"]]["matched_data_version"]
    )


def verify(runtime):
    doc = load_cases()
    rows = read_rows(runtime / "scored-requests.jsonl")
    summaries = json.loads((runtime / "threshold-summary.json").read_text())
    assert len(rows) == 200
    request_ids = {r["response"]["request_id"] for r in rows}
    assert len(request_ids) == 200
    expected_ids = [c["id"] for c in doc["cases"]]
    seed = json.loads((runtime / "seed.json").read_text())
    markers = {
        (r["cache_event"]["dataset_id"], r["cache_event"]["data_version"]) for r in rows
    }
    assert markers == {
        (seed["entries"][0]["dataset_id"], int(seed["entries"][0]["data_version"]))
    }
    assert len(seed["entries"]) == 10
    assert len(summaries) == 5
    for summary in summaries:
        group = [r for r in rows if r["threshold"] == summary["threshold"]]
        assert [r["case_id"] for r in group] == expected_ids
        threshold = summary["threshold"]
        namespace = f"c-sweep-{round(threshold * 100):03d}-01"
        authoritative = cache_events(runtime / f"api-{namespace}-enforced.log")
        raw_rows = read_rows(runtime / f"requests-{threshold:.2f}.jsonl")
        assert len(raw_rows) == 40
        assert set(authoritative) == {r["response"]["request_id"] for r in group}
        sources = {e["source_request_id"]: e for e in seed["entries"]}
        for row, case, raw in zip(group, doc["cases"], raw_rows):
            for field in ("question", "category", "should_hit", "expected"):
                assert row[field] == case[field]
            for field in (
                "question",
                "response",
                "status_code",
                "http_latency_ms",
                "timestamp",
            ):
                assert row[field] == raw[field]
            event = authoritative[row["response"]["request_id"]]
            verify_response(row, event, namespace, threshold)
            assert row["is_cached"] == row["response"]["is_cached"]
            if row["is_cached"]:
                assert event["matched_request_id"] in sources
                source = sources[event["matched_request_id"]]
                assert source["question"] == event["matched_question"]
                assert source["answer"] == row["response"]["answer"]
                assert (
                    int(source["data_version"])
                    == event["matched_data_version"]
                    == event["data_version"]
                )
                assert source["dataset_id"] == event["dataset_id"]
            else:
                assert event["cache_write"] == "stored"
                sources[row["response"]["request_id"]] = {
                    "question": row["question"],
                    "answer": row["response"]["answer"],
                    "data_version": event["data_version"],
                    "dataset_id": event["dataset_id"],
                }
        assert Counter(r["category"] for r in group) == dict.fromkeys(
            ("exact", "paraphrase", "similar_different", "unrelated"), 10
        )
        misses = sum(not r["is_cached"] for r in group)
        wrong_hits = sum(r["is_cached"] and not r["correct"] for r in group)
        assert summary["misses"] == misses
        assert summary["incorrect_cached_answers"] == wrong_hits
        assert summary["total_cost"] == misses * 5 + wrong_hits * 300
        assert all(
            r["status_code"] == 200 and r["cache_event"]["error"] is None for r in group
        )
    audit = json.loads((runtime / "answer-audit.json").read_text())
    decisions = {d["request_id"]: d for d in audit["decisions"]}
    assert len(audit["decisions"]) == len(decisions) == 200
    assert set(decisions) == request_ids
    for row in rows:
        decision = decisions[row["response"]["request_id"]]
        assert decision["automatic_correct"] == row["correct"]
        assert (
            decision["answer_sha256"]
            == hashlib.sha256(row["response"]["answer"].encode()).hexdigest()
        )
        assert (
            decision["case_id"] == row["case_id"]
            and decision["threshold"] == row["threshold"]
        )
        assert isinstance(decision["correct"], bool) and decision["reason"]
        row["automatic_correct"] = row["correct"]
        row["correct"] = decision["correct"]
        row["audit_reason"] = decision["reason"]
    summaries = [
        dict(
            threshold=t,
            **summarize([r for r in rows if r["threshold"] == t], doc["cost_model"]),
        )
        for t in (0.75, 0.80, 0.85, 0.90, 0.95)
    ]
    dump(runtime / "audited-threshold-summary.json", summaries)
    with (runtime / "audited-requests.jsonl").open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    restores = [
        r
        for r in read_rows(runtime / "snapshot-operations.jsonl")
        if r["operation"] == "restore"
    ]
    assert len(restores) == 5 and all(r["entries"] == 10 for r in restores)
    model_events = []
    for stage in ("planner", "writer", "reviewer"):
        model_events.extend(
            r
            for r in read_rows(runtime / f"sweep-{stage}.log")
            if r.get("event") == "model_result"
        )
    model_counts = Counter(e["correlation_id"] for e in model_events)
    assert set(model_counts) <= request_ids
    assert all(e["fixture"] is False for e in model_events)
    for row in rows:
        assert model_counts[row["response"]["request_id"]] == (
            0 if row["is_cached"] else 3
        )
        if not row["is_cached"]:
            events = [
                e
                for e in model_events
                if e["correlation_id"] == row["response"]["request_id"]
            ]
            assert Counter(e["stage"] for e in events) == {
                "planner": 1,
                "writer": 1,
                "reviewer": 1,
            }
            assert (
                next(e["content"] for e in events if e["stage"] == "reviewer")
                == row["response"]["answer"]
            )
    stale = json.loads((runtime / "stale-trace.json").read_text())
    assert [r["response"]["is_cached"] for r in stale] == [False, True, False, True]
    assert stale[0]["response"]["answer"] == stale[1]["response"]["answer"]
    assert (
        stale[1]["cache_event"]["matched_data_version"]
        < stale[1]["cache_event"]["data_version"]
    )
    assert (
        stale[3]["cache_event"]["matched_data_version"]
        == stale[3]["cache_event"]["data_version"]
    )
    mutation = json.loads((runtime / "stale-mutation.json").read_text())
    assert [
        mutation["before"]["availableUnits"],
        mutation["after"]["availableUnits"],
    ] == [3, 1]
    chosen = min(summaries, key=lambda s: (s["total_cost"], -s["threshold"]))[
        "threshold"
    ]
    assert (
        json.loads((runtime / "chosen-threshold.json").read_text())["threshold"]
        == chosen
    )
    verify_demonstrations(runtime, stale, chosen)
    return doc, rows, summaries, stale, model_counts


def verify_restored_entries(runtime):
    import os

    from redis import Redis

    redis = Redis.from_url(os.environ["HW9_REDIS_URL"])
    seed = json.loads((runtime / "seed.json").read_text())
    checks = []
    try:
        for cutoff in (75, 80, 85, 90, 95):
            namespace = f"c-sweep-{cutoff:03d}-01"
            for entry in seed["entries"]:
                key = (
                    f"s6102:hw9:semantic:{namespace}:entry:{entry['source_request_id']}"
                )
                actual = redis.hgetall(key)
                expected = {
                    k.encode(): (
                        base64.b64decode(v) if k == "embedding" else v.encode()
                    )
                    for k, v in entry.items()
                }
                assert actual == expected, key
            checks.append(
                {
                    "namespace": namespace,
                    "seed_entries_byte_identical": 10,
                    "seed_sha256": hashlib.sha256(
                        (runtime / "seed.json").read_bytes()
                    ).hexdigest(),
                }
            )
    finally:
        redis.close()
    dump(runtime / "restored-seed-verification.json", checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    doc, rows, summaries, stale, model_counts = verify(runtime)
    verify_restored_entries(runtime)
    chosen = min(summaries, key=lambda s: (s["total_cost"], -s["threshold"]))
    assert (
        json.loads((runtime / "chosen-threshold.json").read_text())["threshold"]
        == chosen["threshold"]
    )
    false = next(
        r
        for r in rows
        if r["is_cached"] and not r["correct"] and r["category"] == "similar_different"
    )
    source_id = false["cache_event"]["matched_request_id"]
    seed = json.loads((runtime / "seed.json").read_text())
    source = next(
        (e for e in seed["entries"] if e["source_request_id"] == source_id), None
    )
    if source is None:
        source = next(r for r in rows if r["response"]["request_id"] == source_id)
    assert false["response"]["answer"] == source.get(
        "answer", source.get("response", {}).get("answer")
    )
    expected = false["expected"]
    correct_answer = (
        f"{expected['listing_code']} has {expected['value']} available "
        + ("unit." if expected["value"] == 1 else "units.")
        if expected["field"] == "available_units"
        else f"{expected['listing_code']} has property type {expected['value']}."
    )
    false_trace = {
        "scope": "observed frozen sweep, no supplemental diagnostic",
        "threshold": false["threshold"],
        "case_id": false["case_id"],
        "cached_query": false["cache_event"]["matched_question"],
        "incoming_query": false["question"],
        "similarity": false["response"]["similarity"],
        "returned_answer": false["response"]["answer"],
        "correct_fact": false["expected"],
        "correct_answer": correct_answer,
        "request_id": false["response"]["request_id"],
        "source_request_id": source_id,
        "explanation": "Likely embedding confusion: the question template and requested field are identical; only the listing code changes. Their vectors are nearly identical, so cosine similarity does not preserve record identity.",
    }
    dump(runtime / "false-hit-trace.json", false_trace)
    report = [
        "# Part 3: Threshold economics and stale answers",
        "",
        "Pragya Apurva | DATA 260 | November 6, 2026",
        "",
        f"Frozen YAML commit: `{FROZEN_COMMIT}`. SHA-256: `{FROZEN_SHA}`. Labels and costs were committed before the sweep and remain unchanged.",
        "",
        "Ten verified live seed entries were restored into five fresh namespaces. All 200 authenticated requests returned HTTP 200. Fixtures, account, case order, data version, model digests, and generation settings were fixed. The normal store-on-miss behavior stayed enabled within each pass. Restored seed fields and vectors were checked byte for byte after all passes.",
        "",
        "| Threshold | Hits / 40 | Hit rate | Wrong cached / 40 | False-hit rate | Mean HTTP latency (ms) | Misses | Cost (seconds-equivalent) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in summaries:
        report.append(
            f"| {s['threshold']:.2f} | {s['hits']} | {s['hit_rate']:.1%} | {s['incorrect_cached_answers']} | {s['false_hit_rate']:.1%} | {s['mean_http_latency_ms']:.2f} | {s['misses']} | {s['total_cost']} |"
        )
    report += [
        "",
        "Hit rate is hits divided by 40. False-hit rate is factually incorrect cached answers divided by 40. A separate negative-case acceptance rate counts hits on the 20 should-miss cases; it is retained in audited-threshold-summary.json. Wrong live answers are counted separately and do not become false hits. HTTP latency includes the full POST/response interval; server and stage timings are retained per request.",
        "",
        "All answer decisions were reviewed against the full expected facts/rubrics frozen in the YAML. The automatic keyword screen produced two false correctness judgments: a deposit definition mentioned wear and tear without defining it, and a lease definition mentioned responsibilities without explaining a co-signer. answer-audit.json documents both corrections and every reviewed request. Original automatic scores and their preliminary summary remain unchanged in scored-requests.jsonl and threshold-summary.json; this table uses audited-requests.jsonl. No expected fact or should-hit label changed.",
        "",
        "## Costs and choice",
        "",
        "Both costs use seconds-equivalent: a miss costs 5 seconds, a nominal local three-stage generation budget; a wrong cached answer costs 300 seconds, an assumed five-minute support correction. These are fixed illustrative weights, not measured support effort or monetary charges. The nominal miss weight understates the observed miss latency, so the cost column must not be read as measured elapsed time. Total cost = misses × 5 + incorrect cached answers × 300. Actual measured latency remains a separate column.",
        "",
        f"Choose **{chosen['threshold']:.2f}** from the five tested cutoffs: it minimizes the frozen cost at {chosen['total_cost']} seconds-equivalent. The predeclared tie-break chooses the higher threshold. A separate smoke run at this setting returned a fresh miss and then a hit. This threshold still returns {chosen['incorrect_cached_answers']} wrong cached answers in 40 requests. Before production use, matching should also require the same listing identity; version checks alone cannot prevent cross-listing semantic confusion.",
        "",
        "At 0.90 and 0.95, P02's similarity of 0.876015127 falls below the cutoff, so its fresh paraphrase answer enters the cache. P04 then matches that answer from a different listing at 0.999324322. This change in within-pass cache contents helps explain the increase from 13 wrong cached answers at 0.85 to 15 at 0.90 and 0.95. Every pass began with the same seed; normal cache writes remained enabled.",
        "",
        "## One observed false hit",
        "",
        f"- Cached query: {false_trace['cached_query']}",
        f"- Incoming query: {false_trace['incoming_query']}",
        f"- Similarity: {false_trace['similarity']:.9f}; cutoff {false_trace['threshold']:.2f}.",
        f"- Returned cached answer: {false_trace['returned_answer']}",
        f"- Correct answer: {correct_answer}",
        f"- {false_trace['explanation']}",
        "",
        "The trace comes from the frozen sweep. No supplemental diagnostic was needed.",
        "",
        "## Stale answer and version enforcement",
        "",
        "The separate S6102-R-9199 fixture began with 3 available units. An authenticated SQL PUT changed it to 1. In the restricted stale-demo namespace, bypassing the version filter returned the old cached 3. Restarting the same namespace with normal enforcement returned a fresh miss at 1 and then a hit at 1.",
        "",
        "| Step | Cached | Current version | Matched version | Returned answer |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for r in stale:
        e = r["cache_event"]
        report.append(
            f"| {r['step']} | {r['response']['is_cached']} | {e['data_version']} | {e['matched_data_version']} | {r['response']['answer'].replace('|', '/')} |"
        )
    report += [
        "",
        "Rental writes advance one dataset-wide version in the same SQL transaction. Cache lookup filters to the current version before selecting a neighbor, and stale in-flight results are not stored. This is simple and blocks reuse of old facts, but one listing mutation also invalidates unrelated listing answers and may lower the hit rate.",
        "",
        "## Reproduction and evidence",
        "",
        "Use docs/HW9_CACHE.md for the isolated service setup and requirements-hw09-cache.txt. Set private account/database variables and PYTHONPATH=.:code. Run `python -m scripts.hw09.cache_experiments seed --runtime <external-directory>`, review the ten answers, and create seed-reviewed.json. Then run the `sweep` and `stale` phases with the same runtime and configuration. Finally run `python -m scripts.hw09.analyze_cache_experiments --runtime <external-directory>`. Every run requires fresh namespaces, logs, and an owned empty database; use a fresh isolated Redis service for a complete rerun. The shared RuntimeLease directory must be the ollama-shared sibling of that runtime directory.",
        "",
        "Source dependency: B commit `6938c71110845b7b73c53b795b709399f8a523a1`, merged with history. Seed service source: frozen-case commit. Sweep and stale source: runner commit `52c8ef470b124605a0fc51dd8c5821b4a5f3738b`. Hardware, library versions, model digests and settings are in run-metadata.json. Shared lease windows and D's release acknowledgement establish the coordinated exclusive model window. Unrelated Docker workloads remained on the host; these are local single-run latency measurements, without confidence intervals.",
        "",
        "AI use: Codex prepared the synthetic cases, runner, calculations, and evidence text. Expected listing facts, returned seed answers, frozen labels, raw request outputs, and the stale transition were checked directly. The tests distinguish label acceptance from factually wrong answers and ensure listing-code digits cannot count as available-unit facts. The costs are assumptions declared before results. No label edits or supplemental sweep requests were made after results.",
        "",
    ]
    (runtime / "ANALYSIS.md").write_text("\n".join(report))
    verification = {
        "passed": True,
        "requests": 200,
        "thresholds": 5,
        "cases_per_threshold": 40,
        "categories_each": 10,
        "unique_request_ids": 200,
        "http_errors": 0,
        "yaml_commit": FROZEN_COMMIT,
        "yaml_sha256": FROZEN_SHA,
        "seed_sha256": hashlib.sha256((runtime / "seed.json").read_bytes()).hexdigest(),
        "restored_seed_entries_verified": 50,
        "fixed_markers": sorted(
            {
                (r["cache_event"]["dataset_id"], r["cache_event"]["data_version"])
                for r in rows
            }
        ),
        "generative_calls": sum(model_counts.values()),
        "hit_generative_calls": 0,
        "model_calls_per_miss": 3,
        "wrong_live_answers": sum(s["wrong_live_answers"] for s in summaries),
        "chosen_threshold": chosen["threshold"],
        "stale_demo_passed": True,
        "label_changes": 0,
        "automatic_scoring_corrections": sum(
            r["automatic_correct"] != r["correct"] for r in rows
        ),
        "frozen_case_bindings_verified": 200,
        "authoritative_response_events_verified": 206,
        "demonstration_answers_audited": 6,
        "chosen_smoke_verified": True,
        "supplemental_diagnostic_requests": 0,
    }
    dump(runtime / "verification.json", verification)
    output = DATA / "raw/part3"
    output.mkdir(parents=True, exist_ok=True)
    names = [
        "run-metadata.json",
        "seed.json",
        "seed-reviewed.json",
        "seed-review.json",
        "seed-questions.json",
        "seed-requests.jsonl",
        "fixture-receipts.json",
        "snapshot-operations.jsonl",
        "lease-windows.jsonl",
        "scored-requests.jsonl",
        "threshold-summary.json",
        "answer-audit.json",
        "demonstration-audit.json",
        "audited-requests.jsonl",
        "audited-threshold-summary.json",
        "chosen-threshold.json",
        "stale-trace.json",
        "stale-mutation.json",
        "stale-requests.jsonl",
        "chosen-smoke.jsonl",
        "false-hit-trace.json",
        "restored-seed-verification.json",
        "verification.json",
        "ANALYSIS.md",
        "seed-console.txt",
        "sweep-console.txt",
        "stale-console.txt",
    ]
    for pattern in (
        "api-*.log",
        "seed-*.log",
        "sweep-*.log",
        "stale-*.log",
        "requests-*.jsonl",
    ):
        names.extend(p.name for p in runtime.glob(pattern))
    for name in sorted(set(names)):
        shutil.copy2(runtime / name, output / name)
    table_view = [
        "Cutoff   Hit rate    False-hit rate    Mean HTTP ms    Cost (seconds-equivalent)"
    ]
    table_view.extend(
        f"{s['threshold']:.2f}     {s['hit_rate']:6.1%}       {s['false_hit_rate']:6.1%}          {s['mean_http_latency_ms']:9.2f}       {s['total_cost']:5d}"
        for s in summaries
    )
    table_view += [
        "",
        "Fixed costs: miss=5 seconds; wrong cached answer=300 seconds.",
        "Total = miss count x 5 + wrong cached count x 300.",
        f"Chosen cutoff: {chosen['threshold']:.2f}; all 200 requests HTTP 200.",
        "Full frozen-rubric audit corrected two automatic keyword scores.",
        f"Frozen YAML commit: {FROZEN_COMMIT}",
        f"YAML SHA-256: {FROZEN_SHA}",
    ]
    views = {
        "threshold-table": (
            "Part 3.2 and 3.4: Frozen threshold sweep",
            "\n".join(table_view),
        ),
        "false-hit": (
            "Part 3.3: Observed false hit",
            json.dumps(false_trace, indent=2),
        ),
        "stale-answer": (
            "Part 3.5: 3 -> 1 stale answer and version enforcement",
            "\n\n".join(
                f"{r['step']}\ncached={r['response']['is_cached']} current_version={r['cache_event']['data_version']} matched_version={r['cache_event']['matched_data_version']}\n{r['response']['answer']}"
                for r in stale
            ),
        ),
    }
    for name, (title, content) in views.items():
        page = f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title><style>body{{margin:44px;font:19px/1.55 system-ui;color:#172538;background:#f4f6fa}}header{{font-weight:700;color:#174c72}}h1{{font-size:26px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;padding:26px;border:1px solid #bdcbd8;background:white;font:16px/1.6 ui-monospace,monospace}}footer{{font-size:14px}}</style><header>Pragya Apurva | DATA 260 Homework 9</header><h1>{html.escape(title)}</h1><pre>{html.escape(content)}</pre><footer>Evidence view rendered from actual saved run records. Full requests and correlated service logs accompany this screenshot.</footer>"
        (runtime / f"{name}.html").write_text(page)
    write_manifest(output)
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
