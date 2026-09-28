"""Deterministic dataset and fail-closed ownership checks, independent of MySQL."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts/hw04/part3"
sys.path.insert(0, str(SCRIPT_DIR))
from seed_data import assert_empty_seed_target, dataset_checksum, generate_dataset, seed_owned_database, validate_dataset
from ownership import OwnershipError, validate_manifest, validate_observed_target


def ownership_manifest():
    return {
        "format_version": 1,
        "purpose": "hw04-part3-performance",
        "disposable": True,
        "host": "127.0.0.1",
        "port": 13309,
        "database": "s6102_rel",
        "server_uuid": "d8cacfe0-cd61-11ee-96ee-0242ac120002",
        "docker_container_id": "a" * 64,
        "docker_container_name": "hw04-part3-test",
    }


class DatasetTests(unittest.TestCase):
    def test_seed_is_repeatable_and_exactly_balanced(self):
        first = generate_dataset()
        self.assertEqual(first, generate_dataset())
        self.assertEqual(first["seed"], 6102)
        self.assertEqual(len(first["rentals"]), 5000)
        self.assertEqual(len(first["managers"]), 200)
        self.assertEqual(len(dataset_checksum(first)), 64)
        summary = validate_dataset(first)
        self.assertEqual(summary["association_count"], 5000)
        self.assertEqual(summary["distinct_manager_count"], 200)
        self.assertEqual(summary["rentals_per_manager_min"], 25)
        self.assertEqual(summary["rentals_per_manager_max"], 25)
        self.assertEqual(len({r["listing_title"] for r in first["rentals"]}), 5000)

    def test_no_ids_are_supplied_and_domain_values_are_valid(self):
        dataset = generate_dataset()
        for row in dataset["rentals"]:
            self.assertNotIn("id", row)
            self.assertEqual(set(row), {
                "listing_title", "property_address", "submitter_email",
                "description", "property_type", "terms_accepted", "manager_ordinal",
            })
            self.assertTrue(0 < len(row["listing_title"].strip()) <= 255)
            self.assertTrue(0 < len(row["property_address"].strip()) <= 255)
            self.assertRegex(row["submitter_email"], r"^[^@\s]+@example\.com$")
            self.assertGreaterEqual(len(row["description"]), 26)
            self.assertIn(row["property_type"], {"apartment", "house", "condo", "townhouse"})
            self.assertIs(row["terms_accepted"], True)

    def test_checks_detect_foreign_keys_and_edited_content(self):
        dataset = generate_dataset()
        original_checksum = dataset_checksum(dataset)
        dataset["rentals"][0]["manager_ordinal"] = 999
        self.assertNotEqual(original_checksum, dataset_checksum(dataset))
        with self.assertRaises(ValueError):
            validate_dataset(dataset)

    def test_different_seed_changes_generated_data(self):
        self.assertNotEqual(dataset_checksum(generate_dataset()), dataset_checksum(generate_dataset(6103)))

    def test_seed_never_resets_existing_rows(self):
        assert_empty_seed_target(0, 0)
        for counts in [(1, 0), (0, 1), (5000, 200)]:
            with self.subTest(counts=counts), self.assertRaisesRegex(OwnershipError, "no reset/delete/drop"):
                assert_empty_seed_target(*counts)

    def test_bad_ownership_stops_before_session_or_writes(self):
        session_calls = []
        def no_session():
            session_calls.append(True)
            raise AssertionError("Must not open a write session")
        with patch("seed_data.verify_engine_ownership", side_effect=OwnershipError("Unverified target")):
            with self.assertRaisesRegex(OwnershipError, "Unverified target"):
                seed_owned_database(
                    engine=object(), session_factory=no_session, rental_model=object,
                    manager_model=object, ownership_manifest="/tmp/missing.json", schema_revision="001",
                )
        self.assertEqual(session_calls, [])


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ownership_manifest()
        self.observed = {
            "host": "127.0.0.1", "port": 13309, "database": "s6102_rel",
            "server_uuid": self.manifest["server_uuid"], "dialect": "mysql",
            "docker_container_id": "a" * 64, "docker_container_name": "hw04-part3-test",
            "docker_running": True, "docker_bind_host": "127.0.0.1", "docker_bind_port": 13309,
        }

    def test_exact_owned_disposable_target_is_accepted(self):
        self.assertEqual(validate_manifest(self.manifest), self.manifest)
        validate_observed_target(self.manifest, self.observed)

    def test_manifest_rejects_unverified_shared_or_remote_target(self):
        for field, bad_value in [
            ("disposable", False), ("disposable", "true"), ("purpose", "ordinary-development"),
            ("host", "db.example.com"), ("database", "other_database"), ("server_uuid", ""),
            ("docker_container_id", "mysql"), ("port", 0), ("port", True),
        ]:
            with self.subTest(field=field, value=bad_value):
                changed = {**self.manifest, field: bad_value}
                with self.assertRaises(OwnershipError):
                    validate_manifest(changed)

    def test_every_runtime_identity_component_must_match(self):
        for field, bad_value in [
            ("server_uuid", "00000000-0000-0000-0000-000000000000"), ("host", "localhost"),
            ("port", 3306), ("database", "shared"), ("dialect", "sqlite"),
            ("docker_container_id", "b" * 64), ("docker_container_name", "sibling-db"),
            ("docker_running", False), ("docker_bind_host", "0.0.0.0"), ("docker_bind_port", 3306),
        ]:
            with self.subTest(field=field):
                with self.assertRaises(OwnershipError):
                    validate_observed_target(self.manifest, {**self.observed, field: bad_value})

    def test_missing_fields_fail_closed(self):
        for field in self.manifest:
            changed = dict(self.manifest)
            del changed[field]
            with self.subTest(field=field), self.assertRaises(OwnershipError):
                validate_manifest(changed)


if __name__ == "__main__":
    unittest.main()
