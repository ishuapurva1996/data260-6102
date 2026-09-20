"""Offline metric tests use deliberate source hits without answer support."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.retrieval.metrics import markdown_summary, summarize


def fixture():
    run = {
        "run_id": "fixture",
        "techniques": {
            "token": {"stats": {"chunk_count": 9, "average_character_length": 100.0}},
        },
    }
    records = [{
        "question_id": "q1", "question": "What amount?", "designation": "baseline",
        "technique": "token", "expected_source_ids": ["gold", "other_gold"],
        "requested_k": 3, "returned_k": 3, "search_seconds": [0.001, 0.003],
        "hits": [
            {"node_id": "n1", "source_id": "gold", "rank": 1,
             "store_score": 0.9, "cosine": 0.6, "retrieved_text": "Related housing text."},
            {"node_id": "n2", "source_id": "gold", "rank": 2,
             "store_score": 0.8, "cosine": 0.8, "retrieved_text": "Related fees."},
            {"node_id": "n3", "source_id": "not_gold", "rank": 3,
             "store_score": None, "cosine": 0.4, "retrieved_text": "Rent notices."},
        ],
    }]
    annotations = {"annotations": [
        {"question_id": "q1", "technique": "token", "node_id": f"n{i}",
         "central_support": False, "context_support": i == 2,
         "evidence": "The central text only discusses related topics.",
         "rationale": "The requested amount appears only in the n2 window."}
        for i in range(1, 4)
    ]}
    return run, records, annotations


class MetricsTests(unittest.TestCase):
    def test_source_dedup_max_cosine_and_separate_answer_support(self):
        summary = summarize(*fixture())
        row = summary["per_query"][0]
        self.assertEqual(row["source_recall_at_k"], 0.5)
        self.assertEqual(row["retrieved_gold_source_ids"], ["gold"])
        self.assertEqual(row["top1_cosine"], 0.8)  # Not store-rank-1 cosine, 0.6.
        self.assertAlmostEqual(row["mean_at_k_cosine"], 0.6)
        self.assertEqual(row["central_support_at_k"], 0)
        self.assertEqual(row["context_support_at_k"], 1)
        self.assertAlmostEqual(row["mean_search_latency_ms"], 2)
        self.assertEqual(len(summary["high_score_failures"]), 1)
        self.assertEqual(summary["high_score_failures"][0]["node_id"], "n1")

    def test_macro_average_and_diagnostics_are_separate(self):
        run, records, labels = fixture()
        q2 = copy.deepcopy(records[0])
        q2.update(question_id="q2", question="Second?", expected_source_ids=["not_gold"],
                  search_seconds=[0.010])
        diagnostic = copy.deepcopy(q2)
        diagnostic.update(question_id="d1", designation="diagnostic", search_seconds=[0.100])
        records.extend([q2, diagnostic])
        for question_id in ("q2", "d1"):
            for old in labels["annotations"][:3]:
                new = dict(old, question_id=question_id)
                labels["annotations"].append(new)
        summary = summarize(run, records, labels)
        aggregate = summary["baseline"]["techniques"]["token"]
        self.assertEqual(summary["baseline"]["question_count"], 2)
        self.assertEqual(aggregate["source_recall_at_k"], 0.75)
        self.assertEqual(aggregate["mean_search_latency_ms"], 6)
        self.assertEqual(summary["diagnostic"]["techniques"]["token"]["mean_search_latency_ms"], 100)
        self.assertIn("Diagnostic questions", markdown_summary(summary))

    def test_empty_and_fewer_than_k_use_actual_hits(self):
        run, records, labels = fixture()
        records[0]["hits"] = records[0]["hits"][:1]
        records[0]["returned_k"] = 1
        labels["annotations"] = labels["annotations"][:1]
        result = summarize(run, records, labels)
        self.assertEqual(result["per_query"][0]["mean_at_k_cosine"], 0.6)
        records[0].update(hits=[], returned_k=0)
        result = summarize(run, records, {"annotations": []})
        row = result["per_query"][0]
        self.assertIsNone(row["top1_cosine"])
        self.assertIsNone(row["mean_at_k_cosine"])
        self.assertEqual(row["source_recall_at_k"], 0)
        self.assertEqual(row["central_support_at_k"], 0)
        self.assertEqual(row["context_support_at_k"], 0)
        self.assertEqual(result["baseline"]["techniques"]["token"]["cosine_question_count"], 0)
        self.assertTrue(result["diagnostics"])

    def test_missing_duplicate_or_orphan_annotation_fails(self):
        for mutation in ("missing", "duplicate", "orphan"):
            with self.subTest(mutation=mutation):
                run, records, labels = fixture()
                if mutation == "missing":
                    labels["annotations"].pop()
                elif mutation == "duplicate":
                    labels["annotations"].append(dict(labels["annotations"][0]))
                else:
                    labels["annotations"][0]["node_id"] = "unretrieved"
                with self.assertRaises(ValueError):
                    summarize(run, records, labels)

    def test_annotations_must_be_manual_bools_with_evidence_and_rationale(self):
        for key, value in (("central_support", 1), ("context_support", "false"),
                           ("evidence", "  "), ("rationale", "")):
            with self.subTest(key=key):
                run, records, labels = fixture()
                labels["annotations"][0][key] = value
                with self.assertRaises(ValueError):
                    summarize(run, records, labels)

    def test_invalid_numbers_and_inconsistent_k_fail(self):
        for field, value in (("cosine", float("nan")), ("cosine", float("inf")),
                             ("store_score", float("inf")), ("cosine", "0.4")):
            with self.subTest(field=field, value=value):
                run, records, labels = fixture()
                records[0]["hits"][0][field] = value
                with self.assertRaises(ValueError):
                    summarize(run, records, labels)
        for value in ([], [float("nan")], [float("inf")], [-0.1], ["0.1"], [True]):
            with self.subTest(timings=value):
                run, records, labels = fixture()
                records[0]["search_seconds"] = value
                with self.assertRaises(ValueError):
                    summarize(run, records, labels)
        run, records, labels = fixture()
        records[0]["returned_k"] = 2
        with self.assertRaises(ValueError):
            summarize(run, records, labels)

    def test_duplicate_record_and_missing_technique_combination_fail(self):
        run, records, labels = fixture()
        with self.assertRaises(ValueError):
            summarize(run, records * 2, labels)
        run["techniques"]["semantic"] = {"stats": {"chunk_count": 5, "average_character_length": 200}}
        with self.assertRaises(ValueError):
            summarize(run, records, labels)

    def test_cli_regenerates_offline_and_check_never_writes(self):
        run, records, labels = fixture()
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for name, payload in (("run.json", run), ("records.json", records), ("annotations.json", labels)):
                (run_dir / name).write_text(json.dumps(payload), encoding="utf-8")
            output = run_dir / "METRICS.md"
            args = [sys.executable, str(root / "code/retrieval_summarize.py"),
                    "--run-dir", str(run_dir), "--output", str(output)]
            first = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            tracked = [output, run_dir / "summary.json"]
            before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in tracked]
            check = subprocess.run([*args, "--check"], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in tracked])
            output.write_text("corrupted\n", encoding="utf-8")
            check = subprocess.run([*args, "--check"], capture_output=True, text=True)
            self.assertNotEqual(check.returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "corrupted\n")


if __name__ == "__main__":
    unittest.main()


def test_tied_output_order_does_not_change_original_store_rank_one():
    run,records,labels=fixture()
    hits=records[0]['hits']
    hits[0]['store_rank']=2
    hits[1]['store_rank']=1
    hits[2]['store_rank']=3
    result=summarize(run,records,labels)
    assert result['per_query'][0]['store_rank1_cosine']==.8
    assert result['high_score_failures']==[]
