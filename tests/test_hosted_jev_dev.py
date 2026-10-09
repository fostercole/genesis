"""Hosted Jev dev comparison. No network and no GPU."""

import json
import unittest
from pathlib import Path

from toolret_smoke.dev_eval import positive_ranks

from score_hosted_jev_dev import (
    METRIC_KEYS,
    comparison_table,
    load_baselines,
    prefix_length,
    ranks_from_order,
    top1_rate,
)


class HostedJevDevTests(unittest.TestCase):
    def test_prefix_stops_before_the_cap(self):
        self.assertEqual(prefix_length([1.0, 1.0, 1.0], 2.5), 2)
        self.assertEqual(prefix_length([0.1] * 100, 5), 50)
        self.assertEqual(prefix_length([6.0], 5), 0)
        self.assertEqual(prefix_length([5.0], 5), 1)

    def test_probability_order_matches_the_dev_rank_rule(self):
        candidates = [
            {"relevant": True},
            {"relevant": False},
            {"relevant": True},
        ]
        scores = [0.1, 0.5, 0.2]
        order = sorted(range(3), key=lambda index: (-scores[index], index))
        self.assertEqual(
            ranks_from_order(candidates, order, 2),
            positive_ranks(scores, [True, False, True], 2),
        )

    def test_one_returned_tool_leaves_lower_ranks_empty(self):
        candidates = [{"relevant": True}, {"relevant": False}, {"relevant": True}]
        ranks = ranks_from_order(candidates, [2], 2)
        self.assertEqual(ranks, [1, None])
        self.assertEqual(top1_rate([{"ranks": ranks}]), 1.0)
        self.assertEqual(top1_rate([{"ranks": [2, None]}]), 0.0)

    def test_baselines_are_copied_from_the_dev_file(self):
        baselines = load_baselines()
        raw = json.loads(Path("results/dev_bm25_top50.json").read_text())
        self.assertEqual(baselines["locked_k"], 10)
        for name in ("original", "tuned"):
            self.assertEqual(baselines["models"][name]["metrics"], {key: raw["models"][name]["metrics"][key] for key in METRIC_KEYS})
            self.assertEqual(baselines["models"][name]["rows"], 2000)
        self.assertAlmostEqual(baselines["models"]["original"]["metrics"]["ndcg@10"], 0.4985283373562952)
        self.assertEqual(baselines["models"]["original"]["metrics"]["completeness@5"], 0.3495)
        self.assertAlmostEqual(baselines["models"]["tuned"]["metrics"]["ndcg@10"], 0.6877517261865388)
        self.assertEqual(baselines["models"]["tuned"]["metrics"]["completeness@5"], 0.5525)
        self.assertEqual(baselines["models"]["tuned"]["metrics"]["completeness@10"], 0.7225)
        original_top1 = sum(1 for row in raw["models"]["original"]["per_row"] if 1 in row["ranks"]) / 2000
        tuned_top1 = sum(1 for row in raw["models"]["tuned"]["per_row"] if 1 in row["ranks"]) / 2000
        self.assertAlmostEqual(baselines["models"]["original"]["top-1"], original_top1)
        self.assertAlmostEqual(baselines["models"]["tuned"]["top-1"], tuned_top1)

    def test_table_keeps_every_metric_for_all_three_rows(self):
        models = {
            "original": {"metrics": {key: 0.1 for key in METRIC_KEYS}, "top-1": 0.2},
            "tuned": {"metrics": {key: 0.3 for key in METRIC_KEYS}, "top-1": 0.4},
            "hosted_jev": {"metrics": {key: 0.5 for key in METRIC_KEYS}, "top-1": 0.6},
        }
        table = comparison_table(models)
        for label in ("original 2B", "tuned 2B", "hosted Jev", "nDCG@10", "recall@3", "recall@5", "recall@10", "completeness@3", "completeness@5", "completeness@10", "top-1"):
            self.assertIn(label, table)
        self.assertEqual(table.count("\n") + 1, 5)


if __name__ == "__main__":
    unittest.main()
