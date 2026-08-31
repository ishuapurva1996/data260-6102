import os
import shutil
import subprocess
import unittest
from pathlib import Path


WEB_APP_DIR = Path(__file__).parents[3] / "code" / "web_application"


class Part1Tests(unittest.TestCase):
    def test_required_form_controls_are_present(self):
        html = (WEB_APP_DIR / "index_hw1.html").read_text(encoding="utf-8")

        self.assertIn("<title>HW1-Pragya_Apurva</title>", html)
        self.assertIn("<h1>Rental Housing Listings</h1>", html)
        self.assertIn('id="listingTitle"', html)
        self.assertIn("required autofocus", html)
        self.assertIn('type="email"', html)
        self.assertIn("I agree to the terms and conditions.", html)
        self.assertEqual(html.count("<option value="), 5)
        self.assertLess(html.index("</form>"), html.index('<script src="script_hw.js"></script>'))

    def test_javascript_contains_required_language_features(self):
        script = (WEB_APP_DIR / "script_hw.js").read_text(encoding="utf-8")

        self.assertIn("const validateForm = () =>", script)
        self.assertIn("description.length <= 25", script)
        self.assertIn("!termsAccepted.checked", script)
        self.assertIn("JSON.stringify", script)
        self.assertIn("JSON.parse", script)
        self.assertIn("const {listingTitle:", script)
        self.assertIn("...parsedRentalData", script)
        self.assertIn("submissionDate:", script)
        self.assertIn("const submissionCounter = (() =>", script)
        self.assertIn("if (isSubmitting) return", script)
        self.assertIn("submitButton.disabled = true", script)
        self.assertIn("finally {", script)
        self.assertIn("submitButton.disabled = false", script)

    def test_javascript_parses(self):
        node = os.environ.get("NODE_BIN") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is not available for syntax validation")

        completed = subprocess.run(
            [node, "--check", str(WEB_APP_DIR / "script_hw.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
