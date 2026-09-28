"""Offline guards and fixture comparisons; these are not MySQL measurements."""

from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts/hw04/part3"
sys.path.insert(0, str(SCRIPT_DIR))
import index_experiment as experiment


def index_row(name, column, position=1):
    return {"Key_name": name, "Column_name": column, "Seq_in_index": position,
            "Non_unique": 1, "Sub_part": None}


def snapshot(*, indexed=False):
    return {
        "query": experiment.QUERY,
        "parameters": {"title": "HW4-6102-00001 House in Downtown"},
        "dataset": {"stored_dataset_sha256": "a" * 64, "counts": {"rentals": 5000},
                    "physical_rows_sha256": "b" * 64},
        "results": [{"id": 1, "listing_title": "HW4-6102-00001 House in Downtown"}],
        "result_sha256": "c" * 64,
        "indexes": [index_row("PRIMARY", "id")] + (
            [index_row(experiment.INDEX_NAME, "listing_title")] if indexed else []),
        "schema_migrations": [{"version": 1}] + ([{"version": 3}] if indexed else []),
        "explain_traditional": [{"id": 1, "select_type": "SIMPLE", "table": "rentals",
            "type": "ref" if indexed else "ALL", "possible_keys": experiment.INDEX_NAME if indexed else None,
            "key": experiment.INDEX_NAME if indexed else None, "rows": 1 if indexed else 4970,
            "filtered": 100.0 if indexed else 10.0, "Extra": "Using index" if indexed else "Using where"}],
        "explain_format_json_raw": '{"query_block":{"select_id":1}}',
    }


class IndexGuardTests(unittest.TestCase):
    def test_primary_and_manager_indexes_allow_new_experiment(self):
        experiment.assert_unindexed([index_row("PRIMARY", "id"), index_row("manager_fk", "manager_id")], [])

    def test_any_leading_title_index_is_refused_including_composite_and_prefix(self):
        for indexes in [
            [index_row(experiment.INDEX_NAME, "listing_title")],
            [index_row("unrelated_name", "listing_title"), index_row("unrelated_name", "id", 2)],
            [{**index_row("prefix_title", "listing_title"), "Sub_part": 10}],
        ]:
            with self.subTest(indexes=indexes), self.assertRaisesRegex(experiment.IndexExperimentError, "already"):
                experiment.assert_unindexed(indexes, [])

    def test_migration_journal_or_colliding_name_is_refused(self):
        for indexes, journal in [([], [{"version": 3}]), ([index_row(experiment.INDEX_NAME, "description")], [])]:
            with self.subTest(indexes=indexes), self.assertRaises(experiment.IndexExperimentError):
                experiment.assert_unindexed(indexes, journal)

    def test_nonleading_title_column_is_not_mislabeled_as_supporting_equality(self):
        experiment.assert_unindexed([index_row("two_columns", "manager_id"), index_row("two_columns", "listing_title", 2)], [])

    def test_fixture_comparison_uses_observed_estimates_without_assuming_real_row_count(self):
        before, after = snapshot(), snapshot(indexed=True)
        comparison = experiment.compare_snapshots(before, after)
        self.assertEqual(comparison["before"][0]["rows"], 4970)
        self.assertEqual(comparison["after"][0]["rows"], 1)
        self.assertEqual(comparison["before"][0]["access_type"], "ALL")
        self.assertEqual(comparison["after"][0]["key"], experiment.INDEX_NAME)
        self.assertTrue(comparison["equal_results"])

    def test_dataset_parameters_query_and_results_must_remain_identical(self):
        for field, changed in [
            ("query", "SELECT id FROM rentals"), ("parameters", {"title": "changed"}),
            ("dataset", {"stored_dataset_sha256": "changed"}), ("results", []),
            ("result_sha256", "changed"),
        ]:
            with self.subTest(field=field), self.assertRaises(experiment.IndexExperimentError):
                experiment.compare_snapshots(snapshot(), {**snapshot(indexed=True), field: changed})

    def test_success_requires_correct_new_index_and_migration_journal(self):
        for changed in [
            {"indexes": []}, {"indexes": [index_row(experiment.INDEX_NAME, "description")]},
            {"indexes": [{**index_row(experiment.INDEX_NAME, "listing_title"), "Sub_part": 12}]},
            {"schema_migrations": [{"version": 1}]},
        ]:
            with self.subTest(changed=changed), self.assertRaises(experiment.IndexExperimentError):
                experiment.compare_snapshots(snapshot(), {**snapshot(indexed=True), **changed})

    def test_seed_provenance_content_counts_and_server_must_match(self):
        before = snapshot()
        counts = {"rentals": 5000, "property_managers": 200, "associated_rentals": 5000,
                  "distinct_managers": 200, "unique_listing_titles": 5000}
        before["dataset"].update(counts=counts, rental_id_range={"min": 1, "max": 5000})
        owner = {"server_uuid": "fixture-server"}
        before["server"] = {"server_uuid": "fixture-server", "database_name": "s6102_rel"}
        seed = {"seed": 6102, "ownership": owner, "actual_counts": counts,
                "stored_dataset_sha256": "a" * 64, "generated_dataset_sha256": "a" * 64,
                "rental_id_range": {"min": 1, "max": 5000},
                "selective_title": before["parameters"]["title"]}
        experiment.validate_seed_identity(before, seed, owner)
        for changed in [
            {"seed": 9}, {"ownership": {"server_uuid": "another-instance"}},
            {"actual_counts": {**counts, "rentals": 4999}},
            {"stored_dataset_sha256": "changed"}, {"generated_dataset_sha256": "changed"},
            {"rental_id_range": {"min": 2, "max": 5001}}, {"selective_title": "other title"},
        ]:
            with self.subTest(changed=changed), self.assertRaises(experiment.IndexExperimentError):
                experiment.validate_seed_identity(before, {**seed, **changed}, owner)
        with self.assertRaises(experiment.IndexExperimentError):
            experiment.validate_seed_identity({**before, "results": []}, seed, owner)
        with self.assertRaises(experiment.IndexExperimentError):
            experiment.validate_seed_identity({**before, "server": {"server_uuid": "other", "database_name": "s6102_rel"}}, seed, owner)

    def test_failure_is_preserved_and_does_not_invoke_migration_after_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seed = root / "seed.json"
            seed.write_text(json.dumps({"selective_title": "a title"}), encoding="utf-8")
            with patch.object(experiment, "verify_engine_ownership", return_value={}), \
                 patch.object(experiment, "revision_metadata", return_value={"code_revision": "d" * 40}), \
                 patch.object(experiment, "validate_seed_identity"), \
                 patch.object(experiment, "capture_snapshot", return_value=snapshot(indexed=True)), \
                 patch.object(experiment, "apply_index_migration") as migrate:
                with self.assertRaises(experiment.IndexExperimentError) as failure:
                    experiment.run_experiment(engine=object(), ownership_manifest=root / "owner.json",
                                              seed_manifest=seed, output_root=root / "attempts")
            migrate.assert_not_called()
            attempt = failure.exception.attempt_path
            status = json.loads((attempt / "status.json").read_text())
            self.assertEqual(status["status"], "failed")
            self.assertFalse(status["ddl_attempted"])
            self.assertTrue((attempt / "preflight.json").exists())
            self.assertFalse((attempt / "before.json").exists())

    def test_before_evidence_survives_partial_ddl_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seed = root / "seed.json"
            seed.write_text(json.dumps({"selective_title": "a title"}), encoding="utf-8")
            def fail_migration(engine):
                attempts = list((root / "attempts").iterdir())
                self.assertEqual(len(attempts), 1)
                self.assertTrue((attempts[0] / "before.json").exists())
                self.assertTrue((attempts[0] / "explain_before_traditional.json").exists())
                raise RuntimeError("fixture DDL failure")
            with patch.object(experiment, "verify_engine_ownership", return_value={}), \
                 patch.object(experiment, "revision_metadata", return_value={"code_revision": "d" * 40}), \
                 patch.object(experiment, "validate_seed_identity"), \
                 patch.object(experiment, "capture_snapshot", return_value=snapshot()), \
                 patch.object(experiment, "apply_index_migration", side_effect=fail_migration):
                with self.assertRaises(experiment.IndexExperimentError) as failure:
                    experiment.run_experiment(engine=object(), ownership_manifest=root / "owner.json",
                                              seed_manifest=seed, output_root=root / "attempts")
            status = json.loads((failure.exception.attempt_path / "status.json").read_text())
            self.assertTrue(status["ddl_attempted"])
            self.assertEqual(status["failure_stage"], "migration")
            self.assertIn("partial", status["recovery"])


if __name__ == "__main__":
    unittest.main()
