"""A small local REST bridge to one Codex session; `amlr draft` sends its prompts here.

Start it with `amlr bridge` (see pipeline/README.md, "Drafting with Codex"). It sends each
message to one existing Codex task with `codex queue`, follows that task's local rollout
file until the turn completes, and returns the final reply. Requests are serialized, run
in Codex's read-only sandbox, and the server binds to 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

DEFAULT_THREAD_FILE = Path.home() / ".config" / "amlr" / "codex_thread"
MACOS_BUNDLED_CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
MAX_REQUEST_BYTES = 64 * 1024


class BridgeError(RuntimeError):
    """An error safe to expose to the local API caller."""


class CodexBridge:
    def __init__(
        self,
        thread_id: str,
        codex_binary: str,
        workdir: Path,
        timeout_seconds: float,
        rollout_path: Path | None = None,
    ) -> None:
        self.thread_id = thread_id
        self.codex_binary = codex_binary
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds
        self.rollout_path = rollout_path
        # A Codex thread is sequential. Prevent overlapping turns from racing.
        self._turn_lock = threading.Lock()

    def query(self, message: str) -> str:
        with self._turn_lock:
            return self._run_turn(message)

    def _run_turn(self, message: str) -> str:
        request_id = str(uuid.uuid4())
        marker = f"[codex-rest-request:{request_id}]"
        queued_message = (
            f"{marker}\n{message}\n\n"
            "Answer the external query directly. This turn was submitted through the "
            "local REST bridge."
        )
        rollout_path = self.rollout_path or self._find_rollout()
        start_offset = rollout_path.stat().st_size

        command = [
            self.codex_binary,
            "queue",
            "--thread",
            self.thread_id,
            "--message",
            queued_message,
            "--sandbox",
            "read-only",
            "--cd",
            str(self.workdir),
        ]
        try:
            completed = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workdir,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                if len(detail) > 2_000:
                    detail = detail[-2_000:]
                raise BridgeError(
                    f"Codex exited with status {completed.returncode}: {detail}"
                )
            return self._wait_for_reply(rollout_path, start_offset, marker)
        except subprocess.TimeoutExpired as exc:
            raise BridgeError(
                f"Codex queue did not finish within {self.timeout_seconds:g} seconds"
            ) from exc
        except OSError as exc:
            raise BridgeError(f"Could not run Codex: {exc}") from exc

    def _find_rollout(self) -> Path:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        sessions_dir = codex_home / "sessions"
        matches = list(sessions_dir.rglob(f"*-{self.thread_id}.jsonl"))
        if not matches:
            raise BridgeError(f"Could not find the rollout for thread {self.thread_id}")
        return max(matches, key=lambda path: path.stat().st_mtime_ns)

    def _wait_for_reply(self, rollout_path: Path, offset: int, marker: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        matched_turn_id: str | None = None

        with rollout_path.open("rb") as rollout:
            rollout.seek(offset)
            while time.monotonic() < deadline:
                position = rollout.tell()
                raw_line = rollout.readline()
                if not raw_line or not raw_line.endswith(b"\n"):
                    rollout.seek(position)
                    time.sleep(0.1)
                    continue
                try:
                    event = json.loads(raw_line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                payload = event.get("payload", {})
                if matched_turn_id is None and self._message_contains(payload, marker):
                    metadata = payload.get("internal_chat_message_metadata_passthrough", {})
                    matched_turn_id = metadata.get("turn_id")
                    continue

                if payload.get("turn_id") != matched_turn_id or matched_turn_id is None:
                    continue
                if event.get("type") == "event_msg" and payload.get("type") == "task_complete":
                    reply = payload.get("last_agent_message")
                    if isinstance(reply, str) and reply.strip():
                        return reply.strip()
                    raise BridgeError("Codex completed without a final reply")
                if event.get("type") == "event_msg" and payload.get("type") == "turn_aborted":
                    reason = payload.get("reason", "unknown reason")
                    raise BridgeError(f"Codex turn was aborted: {reason}")

        raise BridgeError(
            f"Codex did not finish within {self.timeout_seconds:g} seconds"
        )

    @staticmethod
    def _message_contains(payload: object, marker: str) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("type") != "message" or payload.get("role") != "user":
            return False
        content = payload.get("content", [])
        return any(
            isinstance(item, dict)
            and item.get("type") == "input_text"
            and marker in item.get("text", "")
            for item in content
        )


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        bridge: CodexBridge,
        api_token: str | None,
    ) -> None:
        super().__init__(address, ApiHandler)
        self.bridge = bridge
        self.api_token = api_token


class ApiHandler(BaseHTTPRequestHandler):
    server: ApiServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/query":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized():
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return

        try:
            body = self._read_json()
            message = body.get("message")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("'message' must be a non-empty string")
            request_id = str(uuid.uuid4())
            started = time.monotonic()
            reply = self.server.bridge.query(message.strip())
            self._send_json(
                HTTPStatus.OK,
                {
                    "id": request_id,
                    "reply": reply,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                },
            )
        except ValueError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_request", "detail": str(exc)},
            )
        except BridgeError as exc:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": "codex_error", "detail": str(exc)},
            )

    def _authorized(self) -> bool:
        token = self.server.api_token
        return token is None or self.headers.get("Authorization") == f"Bearer {token}"

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError(f"body must be between 1 and {MAX_REQUEST_BYTES} bytes")
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("body must be a JSON object")
        return value

    def _send_json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def read_thread_id(cli_value: str | None) -> str:
    if cli_value:
        return cli_value.strip()
    env_value = os.environ.get("CODEX_THREAD_ID", "").strip()
    if env_value:
        return env_value
    try:
        file_value = DEFAULT_THREAD_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise SystemExit(
            "No thread configured. Pass --thread-id, set CODEX_THREAD_ID, "
            f"or write the Codex task id to {DEFAULT_THREAD_FILE}."
        ) from exc
    if not file_value:
        raise SystemExit(f"{DEFAULT_THREAD_FILE} is empty")
    return file_value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="amlr bridge", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--thread-id")
    # amlr.codex waits 3300 s for a long section; the bridge gives up a little earlier.
    parser.add_argument("--timeout", type=float, default=3000.0)
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--codex-binary",
        default=find_codex_binary(),
    )
    parser.add_argument(
        "--api-token",
        default=os.environ.get("CODEX_BRIDGE_TOKEN"),
        help="optional bearer token (or set CODEX_BRIDGE_TOKEN)",
    )
    return parser.parse_args(argv)


def find_codex_binary() -> str:
    configured = os.environ.get("CODEX_BINARY")
    if configured:
        return configured
    on_path = shutil.which("codex")
    if on_path:
        return on_path
    if MACOS_BUNDLED_CODEX.is_file():
        return str(MACOS_BUNDLED_CODEX)
    return "codex"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")

    bridge = CodexBridge(
        thread_id=read_thread_id(args.thread_id),
        codex_binary=args.codex_binary,
        workdir=args.workdir.resolve(),
        timeout_seconds=args.timeout,
    )
    try:
        server = ApiServer((args.host, args.port), bridge, args.api_token)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit(
                f"Port {args.port} is already in use. Choose another with --port."
            ) from exc
        raise
    host, port = server.server_address[:2]
    print(f"Codex REST bridge listening on http://{host}:{port}")
    print(f"Bound to thread {bridge.thread_id}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
