import json
import unittest

from toolret_smoke.checks import (
    has_score_spread,
    higher_score_sorts_earlier,
    max_abs_diff,
    scores_match,
)
from toolret_smoke.tools import parse_tool, render_tool


class CheckTests(unittest.TestCase):
    def test_two_runs_match_within_tolerance(self):
        self.assertTrue(scores_match([0.2, -0.1], [0.2 + 1e-6, -0.1]))
        self.assertFalse(scores_match([0.2, -0.1], [0.5, -0.1]))
        self.assertFalse(scores_match([0.2], [0.2, 0.1]))

    def test_higher_score_sorts_earlier(self):
        self.assertTrue(higher_score_sorts_earlier([0.1, 2.0, 2.0, -1.0]))
        self.assertFalse(higher_score_sorts_earlier([1.0]))
        self.assertTrue(has_score_spread([0.0, 1.0]))
        self.assertFalse(has_score_spread([1.0, 1.0]))
        self.assertEqual(max_abs_diff([1.0, 2.0], [1.25, 2.0]), 0.25)

    def test_tool_text_keeps_parameter_names_only(self):
        raw = json.dumps(
            {
                "name": "straddle",
                "description": "Retrieves straddle data.",
                "parameters": {
                    "ticker": {
                        "description": "The stock ticker.",
                        "type": "str",
                        "example": "GOOGL",
                    }
                },
                "example": {"ticker": "GOOGL", "response": "a long example body"},
            }
        )
        tool = parse_tool(raw)
        text = render_tool(tool)
        self.assertIn("straddle:", text)
        self.assertIn("Retrieves straddle data.", text)
        self.assertIn("parameters: ticker", text)
        self.assertNotIn("long example body", text)
        self.assertNotIn("The stock ticker.", text)


if __name__ == "__main__":
    unittest.main()
