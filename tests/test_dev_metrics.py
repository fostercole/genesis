"""Metrics and candidate rules for the dev lock. No GPU."""

import math
import unittest

from toolret_smoke.score_dev import pack_chunks
from toolret_smoke.dev_eval import (
    DEV_SCORE_CAP_USD,
    LOADED_L4_USD_PER_SEC,
    aggregate_metrics,
    assemble_candidates,
    full_pass_estimate_usd,
    lock_k,
    positive_ranks,
    row_metrics,
)


def _tool(name: str, description: str = "d") -> dict:
    return {"name": name, "description": description, "parameters": ["x"], "corpus_id": name}


class DevMetricTests(unittest.TestCase):
    def test_missed_positive_is_injected_and_a_non_positive_is_dropped(self):
        positives = [_tool("gold")]
        bm25 = [_tool(f"bm{i}") for i in range(5)]
        packed = assemble_candidates(positives, bm25, k=5)
        names = [tool["name"] for tool in packed["candidates"]]
        self.assertEqual(len(names), 5)
        self.assertIn("gold", names)
        self.assertNotIn("bm4", names)
        self.assertEqual(packed["n_injected"], 1)
        self.assertEqual(packed["n_positive_in_bm25"], 0)
        self.assertEqual(packed["n_positive_outside"], 0)
        gold = next(tool for tool in packed["candidates"] if tool["name"] == "gold")
        self.assertTrue(gold["relevant"])
        self.assertTrue(gold["injected"])

    def test_positive_already_in_bm25_is_not_injected_twice(self):
        positives = [_tool("gold")]
        bm25 = [_tool("other"), _tool("gold"), _tool("rest")]
        packed = assemble_candidates(positives, bm25, k=3)
        names = [tool["name"] for tool in packed["candidates"]]
        self.assertEqual(names.count("gold"), 1)
        self.assertEqual(packed["n_injected"], 0)
        self.assertEqual(packed["n_positive_in_bm25"], 1)
        self.assertEqual(packed["n_positive_outside"], 0)

    def test_positive_past_k_counts_as_a_miss(self):
        positives = [_tool("g1"), _tool("g2"), _tool("g3")]
        bm25 = [_tool("bm")]
        packed = assemble_candidates(positives, bm25, k=2)
        self.assertEqual(len(packed["candidates"]), 2)
        self.assertEqual(packed["n_positive"], 3)
        self.assertEqual(packed["n_positive_outside"], 1)
        flags = [tool["relevant"] for tool in packed["candidates"]]
        ranks = positive_ranks([0.2, 0.1], flags, packed["n_positive"])
        self.assertIn(None, ranks)
        metrics = row_metrics(ranks, packed["n_positive"])
        self.assertEqual(metrics["completeness@10"], 0.0)
        self.assertAlmostEqual(metrics["recall@10"], 2 / 3)

    def test_ndcg_recall_and_completeness(self):
        # Golds at ranks 1 and 4. Rank 4 is outside @3 and inside @5 and @10.
        ranks = [1, 4]
        metrics = row_metrics(ranks, 2)
        self.assertAlmostEqual(metrics["recall@3"], 0.5)
        self.assertEqual(metrics["completeness@3"], 0.0)
        self.assertAlmostEqual(metrics["recall@5"], 1.0)
        self.assertEqual(metrics["completeness@5"], 1.0)
        self.assertEqual(metrics["completeness@10"], 1.0)
        dcg = 1.0 / math.log2(2) + 1.0 / math.log2(5)
        idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
        self.assertAlmostEqual(metrics["ndcg@10"], dcg / idcg)

    def test_ties_keep_input_order(self):
        ranks = positive_ranks([0.5, 0.5, 0.1], [False, True, False], 1)
        self.assertEqual(ranks, [2])

    def test_aggregate_is_a_macro_average(self):
        rows = [
            {"ranks": [1], "n_positive": 1},
            {"ranks": [None], "n_positive": 1},
        ]
        summary = aggregate_metrics(rows)
        self.assertAlmostEqual(summary["completeness@10"], 0.5)
        self.assertAlmostEqual(summary["recall@10"], 0.5)
        self.assertAlmostEqual(summary["ndcg@10"], 0.5)

    def test_lock_smallest_k_within_one_point(self):
        # 3 is two points behind the best. 5 is one point behind. Lock 5.
        locked = lock_k({3: 0.40, 5: 0.41, 10: 0.42})
        self.assertEqual(locked["locked_k"], 5)
        # Exactly one point still counts as within.
        locked = lock_k({3: 0.41, 5: 0.42, 10: 0.42})
        self.assertEqual(locked["locked_k"], 3)

    def test_pack_chunks_cover_every_index_once(self):
        lengths = [100, 100, 7000, 100, 100, 100]
        chunks = pack_chunks(lengths, budget=1000, max_items=2)
        flat = [index for chunk in chunks for index in chunk]
        self.assertEqual(flat, list(range(len(lengths))))
        self.assertIn([2], chunks)

    def test_estimate_uses_the_loaded_l4_rate(self):
        # 16 probe rows at 1 second, plus 10 seconds to load, over 2,000 rows.
        estimate = full_pass_estimate_usd(load_seconds=10, probe_score_seconds=16, probe_rows=16)
        expected = (10 + 2000) * LOADED_L4_USD_PER_SEC
        self.assertAlmostEqual(estimate, expected)
        self.assertLess(LOADED_L4_USD_PER_SEC * 3600, 1.44)
        self.assertGreater(LOADED_L4_USD_PER_SEC * 3600, 1.42)
        self.assertEqual(DEV_SCORE_CAP_USD, 10.0)


if __name__ == "__main__":
    unittest.main()
