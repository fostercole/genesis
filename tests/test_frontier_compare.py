import json
import tempfile
import unittest
from pathlib import Path

from frontier_compare import (
    ARM_LABELS,
    allocate_modal_costs,
    assign_function_names,
    called_tool,
    example_accuracy,
    graph_points,
    hosted_jev_status,
    keyword_top,
    may_launch,
    parse_tool_calls,
    plot_cost_accuracy,
    qwen_tool_prompt,
    remaining_credit_usd,
    score_top,
    select_rows,
    summarize_arms,
    would_cross_wall,
)


def _tool(name, rank, relevant=False, injected=False, corpus=None):
    return {
        "corpus_id": corpus or name,
        "name": name,
        "description": f"desc {name}",
        "parameters": ["q"],
        "bm25_rank": rank,
        "relevant": relevant,
        "injected": injected,
    }


class FrontierCompareTests(unittest.TestCase):
    def test_credit_wall_and_launch_floor(self):
        self.assertAlmostEqual(remaining_credit_usd(26.12, 0.0), 3.88)
        self.assertEqual(remaining_credit_usd(26.12, 0.5), 0.0)
        self.assertFalse(may_launch(1.99))
        self.assertTrue(may_launch(2.0))
        self.assertTrue(would_cross_wall(2.80, 0.09, 3.88))
        self.assertFalse(would_cross_wall(2.00, 0.08, 3.88))

    def test_keyword_top_is_bm25_order_without_injected(self):
        tools = [_tool("a", 2), _tool("gold", None, relevant=True, injected=True), _tool("b", 0), _tool("c", 1)]
        names = [tool["name"] for tool in keyword_top(tools, k=2)]
        self.assertEqual(names, ["b", "c"])

    def test_score_top_breaks_ties_by_input_order(self):
        tools = [_tool("a", 0), _tool("b", 1), _tool("c", 2)]
        names = [tool["name"] for tool in score_top(tools, [0.2, 0.9, 0.9], k=2)]
        self.assertEqual(names, ["b", "c"])

    def test_function_names_stay_stable_on_a_subset(self):
        tools = [_tool("alpha", 0, corpus="web:tool_1"), _tool("beta", 1, corpus="web:tool_2")]
        names = assign_function_names(tools)
        subset = assign_function_names([tools[1]])
        identity = tools[1]["corpus_id"]
        self.assertEqual(subset[identity], names[identity])

    def test_parser_keeps_the_first_menu_call(self):
        text = '<tool_call>\n{"name": "missing", "arguments": {}}\n</tool_call>\n<tool_call>\n{"name": "keep", "arguments": {}}\n</tool_call>'
        self.assertEqual(parse_tool_calls(text), ["missing", "keep"])
        self.assertEqual(called_tool(text, {"keep"}), "keep")
        self.assertIsNone(called_tool("no call", {"keep"}))

    def test_full_menu_accuracy_is_one_by_construction(self):
        self.assertTrue(example_accuracy("a", "b", "full_menu"))
        self.assertFalse(example_accuracy("a", "b", "keyword_search"))
        examples = [
            {"arms": {"keyword_search": {"match": True}, "original_open_jev_2b": {"match": False}, "tuned_2b": {"match": True}}},
            {"arms": {"keyword_search": {"match": False}, "original_open_jev_2b": {"match": False}, "tuned_2b": {"match": False}}},
        ]
        costs = {arm: 1.0 for arm in ("full_menu", "keyword_search", "original_open_jev_2b", "tuned_2b")}
        summary = summarize_arms(examples, costs)
        self.assertEqual(summary["full_menu"]["accuracy"], 1.0)
        self.assertEqual(summary["keyword_search"]["accuracy"], 0.5)
        self.assertEqual(summary["keyword_search"]["label"], "keyword search")
        self.assertNotIn("bm25", summary["keyword_search"]["label"].lower())
        self.assertTrue(summary["hosted_jev"]["paused"])
        labels = [point["label"] for point in graph_points(summary)]
        self.assertEqual(labels, ["full menu", "keyword search", "original Open-Jev-2B", "tuned 2B"])
        self.assertNotIn("hosted Jev", labels)
        self.assertNotIn("BM25", labels)

    def test_prompt_carries_the_query_and_the_schema(self):
        prompt = qwen_tool_prompt("compute the area", [{"type": "function", "function": {"name": "circle_area"}}])
        self.assertIn("compute the area", prompt)
        self.assertIn("circle_area", prompt)
        self.assertIn("<tool_call>", prompt)

    def test_cost_split_scales_to_the_cli_total(self):
        costs = allocate_modal_costs(
            {"full_menu": 10, "keyword_search": 4, "original_open_jev_2b": 4, "tuned_2b": 4},
            h100_load_seconds=2,
            prefetch_usd=0.2,
            rank_usd=0.4,
            h100_usd_per_second=0.001,
            cli_total_usd=2.0,
        )
        self.assertAlmostEqual(sum(costs.values()), 2.0)
        self.assertGreater(costs["full_menu"], costs["keyword_search"])
        self.assertGreater(costs["tuned_2b"], costs["keyword_search"])

    def test_hosted_jev_paused_when_key_length_is_zero(self):
        status = hosted_jev_status("JEV_API_KEY=\nOTHER=secret\n")
        self.assertTrue(status["in_design"])
        self.assertTrue(status["paused"])
        self.assertFalse(status["called"])
        self.assertIn("empty", status["reason"])
        self.assertNotIn("secret", json.dumps(status))

    def test_selects_ninety_full_pools(self):
        rows = [{"id": str(i), "candidates": [{}] * (50 if i < 95 else 3)} for i in range(100)]
        chosen = select_rows(rows, 90)
        self.assertEqual(len(chosen), 90)
        self.assertEqual(chosen[0]["id"], "0")

    def test_graph_file_is_a_nonempty_png(self):
        points = [
            {"label": "full menu", "modal_cost_usd": 0.4, "accuracy": 1.0},
            {"label": "keyword search", "modal_cost_usd": 0.2, "accuracy": 0.4},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi-cost-accuracy.png"
            plot_cost_accuracy(points, path)
            data = path.read_bytes()
            self.assertGreater(len(data), 0)
            self.assertTrue(data.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
