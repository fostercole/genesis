import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from dogfood.server import INSTRUCTION, Ranker, load_model, make_server, preselect, validate_request
from dogfood.report import summarize


def request(tools=None, **extra):
    return validate_request({"query": "send email", "tools": tools or [
        {"name": "email", "description": "send email", "parameters": {"properties": {"to": {"type": "string"}}}},
        {"name": "calendar", "description": "list events"},
    ], **extra})


class Model:
    tokenizer = object()
    max_length = 384


class DogfoodTests(unittest.TestCase):
    def test_report_compares_off_mode_and_uses_latest_task_rating(self):
        rows = [
            {"event": "task_end", "selection_id": "a", "mode": "off", "wall_ms": 100},
            {"event": "usage", "selection_id": "a", "mode": "off", "input": 1000, "cost_usd": 0.02},
            {"event": "quality", "selection_id": "a", "mode": "off", "rating": "fail"},
            {"event": "quality", "selection_id": "a", "mode": "off", "rating": "pass"},
        ]
        result = summarize(rows)["by_mode"]["off"]
        self.assertEqual(result["completed_tasks"], 1)
        self.assertEqual(result["median_task_wall_ms"], 100)
        self.assertEqual(result["manual_ratings"], {"pass": 1})
        self.assertEqual(result["input_tokens"], 1000)

    def test_validates_names_and_schema_parameter_names(self):
        self.assertEqual(request()["tools"][0]["parameters"], ["to"])
        with self.assertRaises(ValueError):
            request([{"name": "x"}, {"name": "x"}])
        for extra in ({"top_k": True}, {"candidate_limit": 0}, {"budget_ms": 120001}):
            with self.assertRaises(ValueError):
                request(**extra)
        with self.assertRaises(ValueError):
            validate_request({"query": "", "tools": [{"name": "x"}]})

    def test_bm25_uses_query_and_keeps_stable_ties(self):
        tools = [{"name": "calendar", "description": "meetings"},
                 {"name": "sendEmail", "description": "send email", "parameters": ["recipient"]},
                 {"name": "other", "description": "unrelated"}]
        self.assertEqual(preselect("send email", tools, 1)[0]["name"], "sendEmail")
        self.assertEqual(preselect("absentword", tools, 1)[0]["name"], "calendar")
        self.assertEqual(preselect("x", tools, 50), tools)

    def test_scores_independent_candidate_chunks_and_sorts_raw_scores(self):
        calls = []

        def forward(_model, record):
            calls.append(record)
            return [-9.0 if value == "email" else 4.0 for value in record["options"]]

        with patch("dogfood.server.fit_tool_text", side_effect=lambda _t, _q, _i, tool, _m: tool["name"]), \
             patch("dogfood.server._forward", side_effect=forward):
            result = Ranker(Model(), batch_size=1).rank(request(top_k=1))
        self.assertEqual(result["selected"], ["calendar"])
        self.assertEqual(result["ranking"], [{"name": "calendar", "score": 4.0}, {"name": "email", "score": -9.0}])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(len(row["options"]) == 1 for row in calls))
        self.assertTrue(all(row["state"] == "send email" and row["question"] == INSTRUCTION for row in calls))

    def test_bm25_cap_and_batch_size_do_not_change_score_order(self):
        tools = [{"name": str(i), "description": "send email"} for i in range(60)]
        with patch("dogfood.server.fit_tool_text", side_effect=lambda _t, _q, _i, tool, _m: tool["name"]), \
             patch("dogfood.server._forward", side_effect=lambda _m, record: [float(s) for s in record["options"]]):
            a = Ranker(Model(), batch_size=1).rank(request(tools, candidate_limit=50))
            b = Ranker(Model(), batch_size=4).rank(request(tools, candidate_limit=50))
        self.assertEqual(a["selected"], b["selected"])
        self.assertEqual(a["selected"][0], "49")
        self.assertEqual(a["prefilter"], "bm25")
        self.assertEqual(a["candidate_count"], 50)

    def test_timeout_discards_partial_ranking_and_releases_lock(self):
        clock = iter([0, 0, 2])
        ranker = Ranker(Model(), clock=lambda: next(clock))
        with patch("dogfood.server.fit_tool_text", return_value="tool"), \
             patch("dogfood.server._forward", return_value=[1.0]):
            with self.assertRaises(TimeoutError):
                ranker.rank(request(budget_ms=1000))
        self.assertFalse(ranker.lock.locked())

    def test_busy_does_not_queue_requests(self):
        ranker = Ranker(Model())
        ranker.lock.acquire()
        with self.assertRaises(BlockingIOError):
            ranker.rank(request())
        ranker.lock.release()

    def test_nonfinite_scores_fail_and_release_lock(self):
        ranker = Ranker(Model())
        with patch("dogfood.server.fit_tool_text", return_value="tool"), \
             patch("dogfood.server._forward", return_value=[float("nan")]):
            with self.assertRaises(RuntimeError):
                ranker.rank(request())
        self.assertFalse(ranker.lock.locked())

    def test_missing_adapter_or_head_fails_before_importing_torch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "model.json"):
                load_model(Path(directory), "mps", "float32")

    def test_http_validates_input_and_returns_raw_ranking(self):
        class FakeRanker:
            def rank(self, value):
                return {"selected": [value["tools"][0]["name"]], "score_type": "raw"}

        server = make_server(FakeRanker(), "127.0.0.1", 0, {"device": "test"})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(url + "/health") as response:
                self.assertTrue(json.load(response)["ready"])
            req = urllib.request.Request(url + "/rank", data=json.dumps(request()).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(json.load(response)["selected"], ["email"])
            for data, headers, status in [(b"{}", {"Content-Type": "application/json"}, 400),
                (b"{}", {"Content-Type": "application/json", "Origin": "https://example.org"}, 415)]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url + "/rank", data=data, headers=headers))
                self.assertEqual(error.exception.code, status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
