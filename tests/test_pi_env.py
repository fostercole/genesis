import json
import os
import tempfile
import unittest
from pathlib import Path
import pi_loop


class EnvFileTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("JEV_API_KEY", None)

    def test_missing_file_does_not_load_or_create(self):
        missing = Path(tempfile.mkdtemp()) / "nope.env"
        self.assertEqual(pi_loop.load_env_file(missing), {})
        self.assertFalse(pi_loop.load_jev_api_key(missing))
        self.assertNotIn("JEV_API_KEY", os.environ)
        self.assertFalse(missing.exists())

    def test_parser_skips_comments_and_keeps_only_the_jev_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "\n# comment\nexport OTHER_SECRET=nope\nJEV_API_KEY='abc'\nEMPTY=\n"
            )
            parsed = pi_loop.parse_env_text(path.read_text())
            self.assertEqual(parsed["JEV_API_KEY"], "abc")
            self.assertEqual(parsed["EMPTY"], "")
            self.assertTrue(pi_loop.load_jev_api_key(path))
            self.assertEqual(os.environ["JEV_API_KEY"], "abc")
            self.assertNotIn("OTHER_SECRET", os.environ)

    def test_empty_jev_key_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("JEV_API_KEY=\n")
            self.assertFalse(pi_loop.load_jev_api_key(path))
            self.assertNotIn("JEV_API_KEY", os.environ)
            record = pi_loop.hosted_arm_record(False, 0)
            self.assertFalse(record["included"])
            self.assertFalse(record["called"])
            self.assertIn("/workspace/.env", record["reason"])
            self.assertIn("was not called", record["reason"])

    def test_cap_blocks_a_loaded_key(self):
        record = pi_loop.hosted_arm_record(True, 15)
        self.assertFalse(record["included"])
        self.assertFalse(record["called"])
        self.assertIn("$15", record["reason"])

    def test_recorded_spend_reads_pi_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pi_loop.json"
            path.write_text(json.dumps({"spend_usd": 1.5}))
            self.assertEqual(pi_loop.recorded_spend_usd(path), 1.5)
            missing = Path(tmp) / "missing.json"
            self.assertEqual(pi_loop.recorded_spend_usd(missing), 0.0)


if __name__ == "__main__":
    unittest.main()
