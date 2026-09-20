#!/usr/bin/env python3
"""Protocol tests for agent-protocol-bridge.py."""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class UpstreamHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or "0")
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.requests.append({"body": body, "headers": dict(self.headers.items())})
        response = self.server.responses.get(timeout=5)
        data = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def post_json(url, payload, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        cls.upstream.daemon_threads = True
        cls.upstream.requests = []
        cls.upstream.responses = queue.Queue()
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()

        ready = os.path.join(cls.tempdir.name, "ready")
        bridge_script = os.path.join(os.path.dirname(__file__), "agent-protocol-bridge.py")
        cls.bridge = subprocess.Popen(
            [
                sys.executable,
                bridge_script,
                "--port",
                "0",
                "--upstream-base",
                "http://127.0.0.1:%d/v1" % cls.upstream.server_address[1],
                "--api-key-env",
                "TEST_BRIDGE_KEY",
                "--session-id",
                "fallback-session",
                "--ready-file",
                ready,
            ],
            env={**os.environ, "TEST_BRIDGE_KEY": "test-key"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 5
        port = ""
        while time.time() < deadline:
            if os.path.isfile(ready) and os.path.getsize(ready) > 0:
                with open(ready, encoding="utf-8") as handle:
                    port = handle.read().strip()
                break
            if cls.bridge.poll() is not None:
                stderr = cls.bridge.stderr.read()
                raise RuntimeError("bridge exited early: %s" % stderr)
            time.sleep(0.05)
        if not port:
            raise RuntimeError("bridge did not become ready")
        cls.base_url = "http://127.0.0.1:%s" % port

    @classmethod
    def tearDownClass(cls):
        cls.bridge.terminate()
        try:
            cls.bridge.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.bridge.kill()
            cls.bridge.wait(timeout=5)
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.tempdir.cleanup()

    def chat_response(self, content=None, tool_calls=None, finish="stop"):
        message = {"role": "assistant", "content": content, "tool_calls": tool_calls}
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": "glm-5.3-flash",
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }

    def test_responses_text_and_native_session_header(self):
        self.upstream.responses.put(self.chat_response(content="bridge-ok"))
        output = post_json(
            self.base_url + "/v1/responses",
            {
                "model": "glm-5.3-flash",
                "instructions": "Be terse.",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    }
                ],
                "stream": True,
            },
            {"session-id": "native-session", "thread-id": "native-thread"},
        )
        self.assertIn("response.output_text.delta", output)
        self.assertIn("bridge-ok", output)
        upstream = self.upstream.requests[-1]
        self.assertEqual(upstream["body"]["model"], "glm-5.3-flash")
        self.assertEqual(upstream["body"]["messages"][0]["role"], "system")
        self.assertEqual(upstream["headers"]["Session-Id"], "native-session")
        self.assertEqual(upstream["headers"]["X-Opencode-Session"], "native-session")

    def test_responses_tool_call(self):
        self.upstream.responses.put(
            self.chat_response(
                content="",
                tool_calls=[
                    {
                        "id": "call_probe",
                        "type": "function",
                        "function": {"name": "exec_command", "arguments": '{"cmd":"pwd"}'},
                    }
                ],
                finish="tool_calls",
            )
        )
        output = post_json(
            self.base_url + "/v1/responses",
            {
                "model": "glm-5.3-flash",
                "input": [{"type": "message", "role": "user", "content": "run pwd"}],
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "run",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
                "tool_choice": "auto",
                "stream": True,
            },
        )
        self.assertIn("response.function_call_arguments.delta", output)
        self.assertIn('"name":"exec_command"', output)
        self.assertIn('"call_id":"call_probe"', output)

    def test_messages_text_and_tool_result(self):
        self.upstream.responses.put(self.chat_response(content="claude-ok"))
        output = post_json(
            self.base_url + "/v1/messages",
            {
                "model": "glm-5.3-flash",
                "max_tokens": 64,
                "system": "Be terse.",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_probe",
                                "name": "exec_command",
                                "input": {"cmd": "pwd"},
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_probe",
                                "content": "/tmp",
                            }
                        ],
                    },
                ],
                "tools": [
                    {
                        "name": "exec_command",
                        "description": "run",
                        "input_schema": {"type": "object", "properties": {}},
                    }
                ],
                "stream": True,
            },
            {"session-id": "claude-session"},
        )
        self.assertIn("message_start", output)
        self.assertIn("claude-ok", output)
        upstream = self.upstream.requests[-1]
        roles = [message["role"] for message in upstream["body"]["messages"]]
        self.assertEqual(roles, ["system", "assistant", "tool"])
        self.assertEqual(upstream["body"]["messages"][2]["tool_call_id"], "toolu_probe")
        self.assertEqual(upstream["body"]["messages"][2]["content"], "/tmp")
        self.assertEqual(upstream["headers"]["X-Opencode-Session"], "claude-session")


if __name__ == "__main__":
    unittest.main()
