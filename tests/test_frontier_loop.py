"""Credit gate, menus, and the cost chart. No GPU and no Modal."""

import json
import tempfile
import unittest
from pathlib import Path

from frontier_budget import (
    FRONTIER_MODELS,
    allocate_arm_costs,
    choose_plan,
    job_budget,
    may_launch,
    remaining_starter_credit,
    shrink_after_probe,
    spend_cap,
)
from frontier_menu import ARM_LABELS, merge_queries
from frontier_menu import (
    arm_accuracy,
    bm25_top,
    calls_match,
    extract_called_tools,
    sanitize_tool_name,
    select_rows,
)
from frontier_plot import write_cost_accuracy_plot

RATES = {
    "cpu_hour_cost": 0.0473,
    "mem_gib_hour_cost": 0.008,
    "gpu_hour_cost_a100_80gb": 2.5,
    "gpu_hour_cost_l40s": 1.95,
    "gpu_hour_cost_l4": 0.8,
    "gpu_hour_cost_h100": 3.95,
}


def _row(row_id: str, names: list[str], ranks: list[int | None]) -> dict:
    return {
        "id": row_id,
        "query": "Please fetch the pricing chart for this collection today.",
        "n_positive": 1,
        "candidates": [
            {
                "name": name,
                "description": f"desc {name}",
                "parameters": ["q"],
                "corpus_id": f"id-{name}",
                "bm25_rank": rank,
                "relevant": index == 0,
            }
            for index, (name, rank) in enumerate(zip(names, ranks))
        ],
    }


class FrontierBudgetTests(unittest.TestCase):
    def test_remaining_credit_uses_the_larger_of_metered_and_applied(self):
        remaining = remaining_starter_credit(26.13415649, -26.12)
        self.assertAlmostEqual(remaining, 30 - 26.13415649, places=6)
        self.assertTrue(may_launch(remaining))
        self.assertFalse(may_launch(1.99))
        self.assertTrue(may_launch(2))
        self.assertAlmostEqual(spend_cap(remaining), remaining - 1, places=6)
        self.assertAlmostEqual(job_budget(3.211), 3.211, places=6)
        self.assertEqual(job_budget(-1), 0)
        self.assertNotIn("bm25", ARM_LABELS["bm25"].lower())
        self.assertEqual(ARM_LABELS["bm25"], "keyword search")
        self.assertEqual(ARM_LABELS["hosted"], "hosted Jev top 10")

    def test_resume_keeps_finished_arms(self):
        previous = [{"id": "a", "query": "q", "arms": {"full": {"called": ["x"]}, "bm25": {"called": ["x"]}, "original": {"called": ["y"]}, "tuned": {"called": ["x"]}}}]
        extra = [{"id": "a", "arms": {"full": {"called": ["nope"]}, "hosted": {"called": ["x"]}}}, {"id": "b", "query": "q2", "arms": {"hosted": {"called": ["z"]}}}]
        merged = merge_queries(previous, extra)
        self.assertEqual(merged[0]["arms"]["full"]["called"], ["x"])
        self.assertEqual(merged[0]["arms"]["hosted"]["called"], ["x"])
        self.assertEqual(merged[1]["id"], "b")

    def test_full_sample_shrinks_before_a_cheaper_model(self):
        plan = choose_plan(RATES, spend_cap_usd=0.9, full_sample=30)
        self.assertEqual(plan["model"]["key"], "qwen72b-awq")
        self.assertEqual(plan["model"]["gpu"], "H100")
        self.assertLess(plan["sample_size"], 30)
        self.assertGreaterEqual(plan["sample_size"], 1)
        self.assertLessEqual(plan["estimate_usd"], 0.9)
        self.assertTrue(plan["shrunk"])

    def test_one_query_over_cap_steps_down(self):
        tiny = dict(FRONTIER_MODELS[0])
        tiny["load_seconds"] = 20000
        plan = choose_plan(RATES, spend_cap_usd=1.0, full_sample=30, models=(tiny, FRONTIER_MODELS[2]))
        self.assertEqual(plan["model"]["key"], "qwen14b-awq")
        self.assertEqual(plan["rejected"][0]["key"], "qwen72b-awq")

    def test_nothing_fits_under_the_cap(self):
        plan = choose_plan(RATES, spend_cap_usd=0.01, full_sample=30)
        self.assertIsNone(plan["model"])
        self.assertEqual(plan["sample_size"], 0)

    def test_probe_shrinks_the_rest_of_the_sample(self):
        # $0.20 a query after $1.20 spent against a $1.87 cap leaves three more, plus the probe.
        n = shrink_after_probe(20, spent_usd=1.20, seconds_per_query=3600, hourly_usd=0.20, job_cap_usd=1.87, safety=1)
        self.assertEqual(n, 4)

    def test_arm_costs_sum_to_the_cli_total(self):
        costs = allocate_arm_costs(1.25, {"full": 10, "bm25": 5, "original": 5, "tuned": 5})
        self.assertAlmostEqual(sum(costs.values()), 1.25, places=6)
        self.assertAlmostEqual(costs["full"], 0.5, places=6)


class FrontierMenuTests(unittest.TestCase):
    def test_select_rows_stays_on_the_dev_ids(self):
        names = [f"tool{i}" for i in range(50)]
        ranks = list(range(50))
        rows = [
            _row("train_a", names, ranks),
            _row("train_b", names, ranks),
            _row("test_should_not_appear", names, ranks),
        ]
        # Give the second row a distinct query id that is on the dev list.
        chosen = select_rows(rows, {"train_a", "train_b"}, n=2, seed=0)
        self.assertEqual({row["id"] for row in chosen}, {"train_a", "train_b"})

    def test_bm25_top_skips_injected_tools(self):
        candidates = [
            {"name": "injected", "bm25_rank": None},
            {"name": "second", "bm25_rank": 1},
            {"name": "first", "bm25_rank": 0},
        ]
        self.assertEqual([tool["name"] for tool in bm25_top(candidates, 2)], ["first", "second"])

    def test_tool_names_are_unique_and_call_safe(self):
        used: set[str] = set()
        first = sanitize_tool_name("Get Price!", 0, used)
        second = sanitize_tool_name("Get Price!", 1, used)
        self.assertNotEqual(first, second)
        self.assertTrue(first[0].isalpha())
        self.assertNotIn(" ", first)

    def test_extracts_qwen_tool_calls_and_scores_the_filtered_arm(self):
        text = '<tool_call>\n{"name": "get_price", "arguments": {}}\n</tool_call>'
        self.assertEqual(extract_called_tools(text), ["get_price"])
        self.assertEqual(extract_called_tools('{"name": "other", "arguments": {}}'), ["other"])
        self.assertEqual(extract_called_tools("I would use get_price"), [])
        queries = [
            {
                "arms": {
                    "full": {"called": ["get_price"]},
                    "bm25": {"called": ["get_price"]},
                    "original": {"called": ["other"]},
                    "tuned": {"called": []},
                }
            }
        ]
        self.assertTrue(calls_match(["get_price"], ["get_price"]))
        self.assertEqual(arm_accuracy(queries, "full"), 1)
        self.assertEqual(arm_accuracy(queries, "bm25"), 1)
        self.assertEqual(arm_accuracy(queries, "original"), 0)
        self.assertEqual(arm_accuracy(queries, "tuned"), 0)

    def test_plot_writes_a_non_empty_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-cost-accuracy.png"
            write_cost_accuracy_plot(
                [
                    {"label": "full menu", "cost_usd": 0.4, "accuracy": 1},
                    {"label": "keyword search", "cost_usd": 0.2, "accuracy": 0.5},
                ],
                path,
                "probe",
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
