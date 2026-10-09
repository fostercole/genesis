"""Hosted Jev ranking. No network and no GPU."""

import json
import unittest

from attach_hosted_arm import attach
from hosted_jev import (
    HOSTED_LABEL,
    build_choice_body,
    called_call_name,
    rank_indices,
    rank_query,
    redact,
    top_indices,
)


def _tools(n=4):
    return [
        {
            "call_name": f"tool_{index}",
            "name": f"Tool {index}",
            "description": f"desc {index}",
            "parameters": ["q"],
            "corpus_id": f"c{index}",
        }
        for index in range(n)
    ]


class _Response:
    def __init__(self, status, payload):
        self.status = status
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class HostedJevTests(unittest.TestCase):
    def test_choice_body_uses_stable_option_keys(self):
        body = build_choice_body("find a price", _tools(3))
        criteria = body["questions"]["tool"]["criteria"]
        self.assertEqual(list(criteria), ["t00", "t01", "t02"])
        self.assertIn("Tool 1", criteria["t01"])
        self.assertEqual(body["model"], "jev-latest")
        self.assertNotIn("bm25", HOSTED_LABEL.lower())
        self.assertEqual(HOSTED_LABEL, "hosted Jev top 10")

    def test_rank_breaks_probability_ties_by_menu_order(self):
        answer = {"probabilities": {"t00": 0.2, "t01": 0.5, "t02": 0.5, "t03": 0.0}}
        self.assertEqual(rank_indices(answer, 4), [1, 2, 0, 3])

    def test_top_ten_keeps_the_api_choice_first(self):
        tools = _tools(12)
        probabilities = {f"t{index:02d}": 0.01 * index for index in range(12)}
        answer = {"choice": "t01", "probabilities": probabilities}
        top = top_indices(answer, 12, k=10)
        self.assertEqual(top[0], 1)
        self.assertEqual(len(top), 10)
        self.assertNotIn(0, top)
        self.assertEqual(called_call_name(tools, answer), "tool_1")

    def test_rank_query_does_not_echo_the_key(self):
        secret = "super-secret-key"

        def opener(request, timeout):
            header = request.get_header("Authorization") or ""
            self.assertTrue(header.endswith(secret))
            self.assertNotIn(secret, request.data.decode())
            return _Response(
                200,
                {
                    "model": "jev-latest",
                    "answers": {
                        "tool": {
                            "type": "choice",
                            "choice": "t02",
                            "probabilities": {"t00": 0.1, "t01": 0.2, "t02": 0.7},
                            "confidence": 0.4,
                        }
                    },
                    "usage": {"input_tokens": 30, "output_tokens": 4},
                },
            )

        result = rank_query("price", _tools(3), secret, opener=opener, sleep=lambda _seconds: None, attempts=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["called"], "tool_2")
        self.assertEqual(result["top"][0]["call_name"], "tool_2")
        self.assertEqual(result["input_tokens"], 30)
        blob = json.dumps(result)
        self.assertNotIn(secret, blob)
        self.assertEqual(redact(f"failed {secret}", secret), "failed [redacted]")

    def test_auth_failure_is_not_retried_as_success(self):
        calls = {"n": 0}

        def opener(request, timeout):
            calls["n"] += 1
            return _Response(401, {"error": "bad credentials"})

        result = rank_query("price", _tools(2), "k", opener=opener, sleep=lambda _seconds: None, attempts=3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 401)
        self.assertEqual(calls["n"], 1)
        self.assertIsNone(result["called"])
        self.assertNotIn("k", result["error"])

    def test_attach_scores_hosted_choice_against_the_full_menu_call(self):
        record = {
            "model": "Qwen/Qwen2.5-72B-Instruct",
            "sample_size": 2,
            "arms": {
                "full": {"label": "full menu", "accuracy": 1.0, "cost_usd": 0.4},
                "bm25": {"label": "keyword search", "accuracy": 0.5, "cost_usd": 0.2},
            },
            "queries": [
                {"id": "a", "arms": {"full": {"called": ["price"], "seconds": 1}, "bm25": {"called": ["price"], "seconds": 1}}},
                {"id": "b", "arms": {"full": {"called": ["weather"], "seconds": 1}, "bm25": {"called": ["other"], "seconds": 1}}},
            ],
        }
        ranks = {
            "a": {"ok": True, "called": "price", "top": [{"call_name": "price"}], "input_tokens": 1000, "output_tokens": 10, "seconds": 0.2, "model": "jev-1.13.0"},
            "b": {"ok": True, "called": "price", "top": [{"call_name": "price"}], "input_tokens": 1000, "output_tokens": 10, "seconds": 0.2, "model": "jev-1.13.0"},
        }
        updated = attach(record, ranks)
        self.assertEqual(updated["arms"]["hosted"]["label"], "hosted Jev top 10")
        self.assertEqual(updated["arms"]["hosted"]["accuracy"], 0.5)
        self.assertEqual(updated["arms"]["hosted"]["cost_usd"], 0.0)
        self.assertAlmostEqual(updated["hosted_jev"]["api_cost_usd"], 2000 * 0.042 / 1_000_000)
        self.assertTrue(updated["hosted_jev"]["called"])
        self.assertNotIn("bm25", updated["arms"]["bm25"]["label"].lower())


if __name__ == "__main__":
    unittest.main()
