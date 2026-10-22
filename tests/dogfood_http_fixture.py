"""Protocol fixture for the Pi integration test. Does not load model weights."""
from dogfood.server import make_server


class FixtureRanker:
    def rank(self, value):
        ranked = [{"name": tool["name"], "score": float(index)} for index, tool in enumerate(value["tools"])]
        ranked.sort(key=lambda row: -row["score"])
        return {"selected": [row["name"] for row in ranked[:value["top_k"]]], "ranking": ranked,
                "input_count": len(ranked), "candidate_count": len(ranked), "prefilter": "none",
                "elapsed_ms": 1.0, "score_type": "raw_logit_not_calibrated_probability"}


if __name__ == "__main__":
    server = make_server(FixtureRanker(), "127.0.0.1", 0, {"fixture": True})
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()
