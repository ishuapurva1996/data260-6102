import os
import shutil
import subprocess
import unittest
from pathlib import Path


WEB_APP_DIR = Path(__file__).parents[3] / "code" / "web_application" / "static"


class Part1Tests(unittest.TestCase):
    def test_required_form_controls_are_present(self):
        html = (WEB_APP_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("<h1>Rental Housing Listings</h1>", html)
        self.assertIn('id="listingTitle"', html)
        self.assertIn("required autofocus", html)
        self.assertIn('type="email"', html)
        self.assertIn("I agree to the terms and conditions.", html)
        self.assertEqual(html.count("<option value="), 5)
        self.assertIn('id="updateForm"', html)
        self.assertIn('id="searchForm"', html)
        self.assertIn('id="deleteHighestButton"', html)
        self.assertLess(html.index("</form>"), html.index('<script src="/static/app.js"></script>'))

    def test_accessible_feedback_and_local_assets(self):
        # The original HW1 language-feature demonstration is preserved at its
        # Git tag. Live API behavior is covered by tests/test_api.py and the
        # browser walkthrough; retain the form's accessibility/asset contract.
        html = (WEB_APP_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="emptyState"', html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('href="/static/styles.css"', html)
        self.assertTrue((WEB_APP_DIR / "styles.css").is_file())
        self.assertTrue((WEB_APP_DIR / "app.js").is_file())

    def test_javascript_parses(self):
        node = os.environ.get("NODE_BIN") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is not available for syntax validation")

        completed = subprocess.run(
            [node, "--check", str(WEB_APP_DIR / "app.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
