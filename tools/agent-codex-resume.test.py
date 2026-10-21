#!/usr/bin/env python3

import base64
import hashlib
import json
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("agent-codex-resume.py")
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
THREAD_ID = "11111111-2222-4333-8444-555555555555"


def recv_exact(stream: socket.socket, size: int) -> bytes:
    chunks = []
    while size:
        chunk = stream.recv(size)
        if not chunk:
            raise ConnectionError("closed")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def recv_http(stream: socket.socket) -> str:
    data = b""
    while b"\r\n\r\n" not in data:
        data += stream.recv(4096)
    return data.decode("latin-1")


def send_frame(stream: socket.socket, payload: dict) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(raw) < 126:
        header = bytes((0x81, len(raw)))
    else:
        header = bytes((0x81, 126)) + struct.pack("!H", len(raw))
    stream.sendall(header + raw)


def recv_frame(stream: socket.socket) -> dict | None:
    first, second = recv_exact(stream, 2)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", recv_exact(stream, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(stream, 8))[0]
    mask = recv_exact(stream, 4) if second & 0x80 else b""
    payload = recv_exact(stream, length)
    if mask:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    if opcode == 0x8:
        return None
    if opcode != 0x1:
        return {}
    return json.loads(payload.decode("utf-8"))


class FakeAppServer:
    def __init__(self, path: Path, *, fail_resume: bool = False) -> None:
        self.path = path
        self.fail_resume = fail_resume
        self.methods: list[str] = []
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise TimeoutError("fake app-server did not stop")
        if self.error:
            raise self.error

    def _run(self) -> None:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.path))
            server.listen(1)
            server.settimeout(5)
            connection, _ = server.accept()
            connection.settimeout(5)
            request = recv_http(connection)
            key = ""
            for line in request.split("\r\n"):
                name, separator, value = line.partition(":")
                if separator and name.lower() == "sec-websocket-key":
                    key = value.strip()
            accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
            connection.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n"
                    "\r\n"
                ).encode("ascii")
            )
            while True:
                event = recv_frame(connection)
                if event is None:
                    break
                method = event.get("method")
                if method:
                    self.methods.append(method)
                request_id = event.get("id")
                if method == "initialize" and request_id is not None:
                    send_frame(
                        connection,
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "codexHome": "/tmp",
                                "platformFamily": "unix",
                                "platformOs": "linux",
                                "userAgent": "fake",
                            },
                        },
                    )
                elif method == "thread/resume" and request_id is not None:
                    if self.fail_resume:
                        send_frame(
                            connection,
                            {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "error": {"code": -32600, "message": "resume failed"},
                            },
                        )
                        break
                    send_frame(
                        connection,
                        {"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}},
                    )
                elif method == "thread/queue/add" and request_id is not None:
                    send_frame(
                        connection,
                        {
                            "jsonrpc": "2.0",
                            "method": "thread/queue/changed",
                            "params": {"threadId": THREAD_ID},
                        },
                    )
                    send_frame(
                        connection,
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "queuedSubmission": {
                                    "id": "queued-1",
                                    "clientUserMessageId": event["params"]["clientUserMessageId"],
                                    "input": event["params"]["input"],
                                }
                            },
                        },
                    )
                elif method == "thread/queue/start" and request_id is not None:
                    send_frame(
                        connection,
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {"turn": {"id": "turn-1", "status": "inProgress"}},
                        },
                    )
            connection.close()
        except BaseException as error:
            self.error = error
        finally:
            server.close()


class CodexResumeTests(unittest.TestCase):
    def _run(self, root: Path, *, fail_resume: bool = False) -> tuple[subprocess.CompletedProcess[str], FakeAppServer]:
        sock = root / "app.sock"
        server = FakeAppServer(sock, fail_resume=fail_resume)
        server.start()
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--remote",
                f"unix://{sock}",
                "--thread",
                THREAD_ID,
                "--message",
                "继续",
                "--timeout",
                "3",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        server.join()
        return result, server

    def test_resumes_thread_and_starts_queued_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            result, server = self._run(Path(temp))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"thread_id={THREAD_ID}", result.stdout)
            self.assertIn("queued_id=queued-1", result.stdout)
            self.assertIn("turn_id=turn-1", result.stdout)
            self.assertEqual(
                server.methods,
                ["initialize", "initialized", "thread/resume", "thread/queue/add", "thread/queue/start"],
            )

    def test_resume_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            result, _server = self._run(Path(temp), fail_resume=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("thread/resume_failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
