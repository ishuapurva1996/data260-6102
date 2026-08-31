import unittest
from types import SimpleNamespace

from src.model_client import OllamaModelClient


class FakeChatModel:
    def __init__(self):
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(
            content="- The function needs an empty-list guard.",
            usage_metadata={
                "input_tokens": 18,
                "output_tokens": 9,
                "total_tokens": 27,
            },
            response_metadata={},
        )


class ModelClientTests(unittest.TestCase):
    def test_complete_normalizes_usage_and_updates_cumulative_stats(self):
        model = FakeChatModel()
        client = OllamaModelClient(model)

        result = client.complete([("user", "Review this function")])

        self.assertEqual(result.content, "- The function needs an empty-list guard.")
        self.assertEqual(result.usage.input_tokens, 18)
        self.assertEqual(result.usage.output_tokens, 9)
        self.assertEqual(result.usage.total_tokens, 27)
        self.assertEqual(client.stats.turn_count, 1)
        self.assertEqual(client.stats.input_tokens, 18)
        self.assertEqual(client.stats.output_tokens, 9)

    def test_missing_total_is_derived_from_input_and_output(self):
        model = FakeChatModel()
        model.invoke = lambda _messages: SimpleNamespace(
            content="- Looks good.",
            usage_metadata={},
            response_metadata={"prompt_eval_count": 12, "eval_count": 4},
        )
        client = OllamaModelClient(model)

        result = client.complete([("user", "Review")])

        self.assertEqual(result.usage.total_tokens, 16)


if __name__ == "__main__":
    unittest.main()
