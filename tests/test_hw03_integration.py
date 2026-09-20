"""Focused contracts for the aggregate verifier's failure propagation."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'verify_hw03', Path(__file__).resolve().parents[1] / 'scripts/verify_hw03.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class AggregateVerifierTests(unittest.TestCase):
    def execute(self, code, status=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'result.json'
            program = (
                'import json,sys; from pathlib import Path; '
                + (f'Path(sys.argv[1]).write_text(json.dumps({{"status": {status!r}}})); '
                   if status is not None else '')
                + 'print("captured output"); '
                + f'sys.exit({code})')
            result = verifier.execute_check(
                'fake', [sys.executable, '-c', program, str(output)], root, root, output)
            self.assertEqual((root / 'fake.txt').read_text().strip(), 'captured output')
            return result

    def test_pass_requires_successful_process_and_pass_payload(self):
        self.assertEqual(self.execute(0, 'pass')['status'], 'pass')

    def test_nonzero_process_cannot_be_masked_by_pass_payload(self):
        result = self.execute(1, 'pass')
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['exit_code'], 1)

    def test_zero_exit_does_not_override_failed_payload(self):
        self.assertEqual(self.execute(0, 'fail')['status'], 'fail')

    def test_missing_payload_does_not_pass(self):
        self.assertEqual(self.execute(0)['status'], 'fail')

    def test_missing_executable_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = verifier.execute_check(
                'missing', [str(root / 'nonexistent')], root, root, root / 'result.json')
            self.assertEqual(result['status'], 'fail')
            self.assertIsNone(result['exit_code'])
            self.assertTrue((root / 'missing.txt').read_text())

    def test_report_manifest_detects_changed_pdf_and_missing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'reports/hw03'
            report.mkdir(parents=True)
            pdf = report / 'report.pdf'
            pdf.write_bytes(b'%PDF-1.4\nreview\n%%EOF\n')
            source = root / 'report-source.md'
            source.write_text('original report source')
            manifest = {
                'pdf_sha256': verifier.sha256(pdf),
                'source_sha256': {'report-source.md': verifier.sha256(source)},
                'page_count': 1, 'tested_code_commit': 'a' * 40,
            }
            (report / 'report-build.json').write_text(json.dumps(manifest))
            valid, _ = verifier.check_report_manifest(root, check_ancestor=lambda commit: True)
            self.assertTrue(valid)
            pdf.write_bytes(b'%PDF-1.4\nchanged\n%%EOF\n')
            valid, _ = verifier.check_report_manifest(root, check_ancestor=lambda commit: True)
            self.assertFalse(valid)
            manifest['pdf_sha256'] = verifier.sha256(pdf)
            (report / 'report-build.json').write_text(json.dumps(manifest))
            source.unlink()
            valid, _ = verifier.check_report_manifest(root, check_ancestor=lambda commit: True)
            self.assertFalse(valid)

    def test_report_manifest_rejects_unrelated_code_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'reports/hw03'
            report.mkdir(parents=True)
            pdf = report / 'report.pdf'
            pdf.write_bytes(b'%PDF-1.4\n%%EOF\n')
            source = root / 'source.md'
            source.write_text('report')
            (report / 'report-build.json').write_text(json.dumps({
                'pdf_sha256': verifier.sha256(pdf), 'source_sha256': {'source.md': verifier.sha256(source)},
                'page_count': 1, 'tested_code_commit': 'b' * 40,
            }))
            valid, _ = verifier.check_report_manifest(root, check_ancestor=lambda commit: False)
            self.assertFalse(valid)


if __name__ == '__main__':
    unittest.main()
