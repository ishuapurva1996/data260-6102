import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "verify_hw01.py"
SPEC = importlib.util.spec_from_file_location("verify_hw01", MODULE_PATH)
verify_hw01 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verify_hw01)


class VerificationTests(unittest.TestCase):
    def test_checked_in_submission_artifacts_are_valid(self):
        passed, detail = verify_hw01.validate_markdown_deliverables()

        self.assertTrue(passed, detail)
        self.assertIn("5 assignment-required Markdown files", detail)

        markdown_paths = {
            path for path, _checks in verify_hw01.MARKDOWN_REQUIREMENTS.values()
        }
        self.assertTrue(markdown_paths.issubset(set(verify_hw01._required_files().values())))

        passed, detail = verify_hw01.validate_pdf(
            Path(__file__).parents[1] / "report.pdf"
        )

        self.assertTrue(passed, detail)
        self.assertIn("page objects", detail)

    def test_rejects_invalid_submission_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            incomplete = Path(directory) / "AI_USE.md"
            incomplete.write_text("# AI Assistant Use\n", encoding="utf-8")
            requirements = {
                "AI_USE.md": (
                    incomplete,
                    (
                        ("AI-use answer", r"^## 1\. What I used"),
                        ("change explanation", r"^## 4\. What I changed"),
                    ),
                )
            }

            markdown_passed, markdown_detail = (
                verify_hw01.validate_markdown_deliverables(requirements)
            )
            report = Path(directory) / "report.pdf"
            report.write_bytes(b"%PDF-1.7\n")
            pdf_passed, pdf_detail = verify_hw01.validate_pdf(report)

        self.assertFalse(markdown_passed)
        self.assertIn("AI_USE.md", markdown_detail)
        self.assertIn("change explanation", markdown_detail)
        self.assertFalse(pdf_passed)
        self.assertIn("small", pdf_detail)

        with tempfile.TemporaryDirectory() as directory:
            stuffed = Path(directory) / "METRICS.md"
            stuffed.write_text(
                "acceptable not acceptable p50 p95 p99 distinct tag sets\n",
                encoding="utf-8",
            )
            requirements = {
                "METRICS.md": (
                    stuffed,
                    (
                        ("interpretation section", r"^## Interpretation$"),
                        (
                            "acceptable-variation example",
                            r"^Run-to-run variation is acceptable when\b",
                        ),
                        (
                            "unacceptable-variation example",
                            r"\bIt is not acceptable when\b",
                        ),
                    ),
                )
            }

            passed, detail = verify_hw01.validate_markdown_deliverables(requirements)

        self.assertFalse(passed)
        self.assertIn("interpretation section", detail)
        self.assertIn("acceptable-variation example", detail)

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "README.md"
            requirements = {
                "README.md": (
                    missing,
                    (("Part 1 heading", r"^## Part 1 - Web application$"),),
                )
            }

            passed, detail = verify_hw01.validate_markdown_deliverables(requirements)

        self.assertFalse(passed)
        self.assertIn("README.md", detail)
        self.assertIn("could not read file", detail)


if __name__ == "__main__":
    unittest.main()
