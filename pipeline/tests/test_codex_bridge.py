import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amlr.codex_bridge import BridgeError, CodexBridge


class CodexBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.rollout = Path(self.tempdir.name) / "rollout.jsonl"
        self.rollout.write_text("", encoding="utf-8")
        self.bridge = CodexBridge(
            thread_id="test-thread",
            codex_binary="codex",
            workdir=Path.cwd(),
            timeout_seconds=30,
            rollout_path=self.rollout,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @patch("amlr.codex_bridge.subprocess.run")
    def test_returns_last_message(self, run) -> None:
        def fake_run(command, **kwargs):
            queued_message = command[command.index("--message") + 1]
            marker = queued_message.splitlines()[0]
            events = [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": queued_message}],
                        "internal_chat_message_metadata_passthrough": {
                            "turn_id": "turn-1"
                        },
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": "turn-1",
                        "last_agent_message": "hello from Codex",
                    },
                },
            ]
            with self.rollout.open("a", encoding="utf-8") as output:
                for event in events:
                    output.write(json.dumps(event) + "\n")
            self.assertTrue(marker.startswith("[codex-rest-request:"))
            return subprocess.CompletedProcess(command, 0, "", "")

        run.side_effect = fake_run
        self.assertEqual(self.bridge.query("hello"), "hello from Codex")
        command = run.call_args.args[0]
        self.assertIn("read-only", command)
        self.assertEqual(command[1], "queue")
        self.assertIn("hello", command[command.index("--message") + 1])

    @patch("amlr.codex_bridge.subprocess.run")
    def test_nonzero_exit_is_reported(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 7, "", "failure")
        with self.assertRaisesRegex(BridgeError, "status 7: failure"):
            self.bridge.query("hello")

    @patch("amlr.codex_bridge.subprocess.run")
    def test_timeout_is_reported(self, run) -> None:
        run.side_effect = subprocess.TimeoutExpired(["codex"], 30)
        with self.assertRaisesRegex(BridgeError, "queue did not finish within 30 seconds"):
            self.bridge.query("hello")


if __name__ == "__main__":
    unittest.main()
