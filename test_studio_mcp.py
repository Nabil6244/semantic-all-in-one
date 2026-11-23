"""studio_mcp.py speaks MCP over stdio and its tools refuse bad input without starting anything."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class StudioMcpTest(unittest.TestCase):
    def talk(self, *msgs):
        data = "".join(json.dumps(m) + "\n" for m in msgs)
        out = subprocess.run([sys.executable, str(HERE / "studio_mcp.py")], input=data, capture_output=True, text=True, timeout=60)
        return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]

    def call(self, name, args=None, mid=9):
        return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}

    def test_handshake_and_tools(self):
        r = self.talk({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                      {"jsonrpc": "2.0", "method": "notifications/initialized"},
                      {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(r), 2)                       # the notification gets no reply
        self.assertEqual(r[0]["result"]["protocolVersion"], "2025-06-18")
        names = {t["name"] for t in r[1]["result"]["tools"]}
        self.assertEqual(names, {"list_styles", "get_csv_prompt", "start_video", "job_status", "list_jobs", "stop_job", "queue_overnight"})

    def test_styles_and_prompt(self):
        r = self.talk(self.call("list_styles", mid=1), self.call("get_csv_prompt", {"style": "war"}, mid=2))
        self.assertIn("war:", r[0]["result"]["content"][0]["text"])
        self.assertFalse(r[1]["result"]["isError"])
        self.assertGreater(len(r[1]["result"]["content"][0]["text"]), 200)

    def test_bad_input_starts_nothing(self):
        r = self.talk(self.call("get_csv_prompt", {"style": "nope"}, mid=1),
                      self.call("start_video", {"style": "war"}, mid=2),          # war needs a voiceover
                      self.call("job_status", {"job": "job_missing"}, mid=3),
                      self.call("stop_job", {"job": "job_missing"}, mid=4),
                      self.call("queue_overnight", {"videos": []}, mid=5),
                      {"jsonrpc": "2.0", "id": 6, "method": "nope"})
        for res in r[:5]:
            self.assertTrue(res["result"]["isError"], res)
        self.assertIn("voice", r[1]["result"]["content"][0]["text"])
        self.assertEqual(r[5]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
