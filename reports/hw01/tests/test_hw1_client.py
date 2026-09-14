import copy
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[3] / "code" / "hw1_client.py"
SPEC = importlib.util.spec_from_file_location("hw1_client", MODULE_PATH)
hw1_client = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(hw1_client)
from src.model_client import CumulativeUsage


class Hw1ClientTests(unittest.TestCase):
    def test_bullet_only_validation(self):
        self.assertTrue(hw1_client.is_bullet_only("- First finding\n- Second finding"))
        self.assertFalse(hw1_client.is_bullet_only("Review\n- First finding"))
        self.assertFalse(hw1_client.is_bullet_only(""))

    def test_stats_does_not_mutate_history(self):
        history = [
            {"role": "user", "content": "Review this function."},
            {"role": "assistant", "content": "- Add an empty-list guard."},
        ]
        before = copy.deepcopy(history)
        usage = CumulativeUsage(turn_count=1, input_tokens=25, output_tokens=8)

        stats = hw1_client.conversation_stats(history, usage)

        self.assertEqual(history, before)
        self.assertEqual(stats["turn_count"], 1)
        self.assertEqual(stats["cumulative_input_tokens"], 25)
        self.assertGreater(stats["serialized_history_characters"], 0)

    def test_save_output_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "raw" / "conversation.txt"

            hw1_client.save_output(output, "recorded output\n")

            self.assertEqual(output.read_text(encoding="utf-8"), "recorded output\n")

    def test_tee_stream_writes_to_terminal_and_transcript(self):
        terminal = io.StringIO()
        transcript = io.StringIO()
        stream = hw1_client.TeeStream(terminal, transcript)

        written = stream.write("visible and recorded\n")
        stream.flush()

        self.assertEqual(written, 21)
        self.assertEqual(terminal.getvalue(), "visible and recorded\n")
        self.assertEqual(transcript.getvalue(), terminal.getvalue())


if __name__ == "__main__":
    unittest.main()
