#!/usr/bin/env python3

import json
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).with_name("agent-session-state.py")
RUN_ID = "20261021T031022.multiplex"
CREATED_AT = "2026-10-21T03:10:22+0800"
TRANSIENT_TEXT = (
    "Upstream request failed: [invalid_request_error] The `reasoning_content` "
    "in the thinking mode must be passed back to the API."
)


class SessionStateTests(unittest.TestCase):
    def test_concurrency_limit_variants_are_transient(self):
        namespace = runpy.run_path(str(SCRIPT), run_name="agent_session_state_test")
        is_transient = namespace["error_is_transient"]
        phrases = (
            "Concurrency limit reached",
            "Too many concurrent requests",
            "HTTP 429: concurrency limit",
            "maximum concurrent sessions exceeded",
            "parallel request limit reached",
            "status code 429",
            "并发上限",
            "并发请求数超限",
            "并发连接数已达上限",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(is_transient(phrase))
        self.assertTrue(is_transient({"http_status_code": 429}))
        self.assertTrue(is_transient({"status": 429, "message": "request rejected"}))
        self.assertTrue(is_transient({"concurrency_limit_exceeded": {}}))

    def test_opencode_v2_failed_idle_without_assistant_error_is_failure(self):
        namespace = runpy.run_path(str(SCRIPT), run_name="agent_session_state_test")
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                "CREATE TABLE session_message (session_id TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL, seq INTEGER NOT NULL, id TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO session_message VALUES (?, ?, ?, ?, ?)",
                ("session-1", "idle", json.dumps({"outcome": "failed"}), 1, "idle-1"),
            )
            result = namespace["opencode_completion_error"](connection, "session-1", 2)
        self.assertEqual(result, (True, False, True, "completed"))

    def _run_lookup(
        self,
        agent: str,
        cwd: Path,
        *,
        data_dir: Path | None = None,
        state_db: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--agent",
            agent,
            "--run-id",
            RUN_ID,
            "--cwd",
            str(cwd),
            "--created-at",
            CREATED_AT,
        ]
        if data_dir is not None:
            command += ["--data-dir", str(data_dir)]
        if state_db is not None:
            command += ["--state-db", str(state_db)]
        return subprocess.run(command, text=True, capture_output=True, check=False)

    @staticmethod
    def _created_ms() -> int:
        return int(datetime.strptime(CREATED_AT, "%Y-%m-%dT%H:%M:%S%z").timestamp() * 1000)

    def test_claude_finds_session_and_classifies_latest_api_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "claude"
            cwd = root / "workspace"
            project = config / "projects" / "-root-workspace"
            project.mkdir(parents=True)
            cwd.mkdir()
            session_id = "11111111-2222-4333-8444-555555555555"
            session_file = project / f"{session_id}.jsonl"
            events = [
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(cwd),
                    "timestamp": "2026-10-21T03:10:23.000Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": f"runtime\nrun_id={RUN_ID}\n"}],
                    },
                },
                {
                    "type": "assistant",
                    "isApiErrorMessage": True,
                    "sessionId": session_id,
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": TRANSIENT_TEXT}],
                    },
                },
                {"type": "system", "subtype": "turn_duration", "sessionId": session_id},
            ]
            session_file.write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )

            result = self._run_lookup("claude", cwd, data_dir=config)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"session_id={session_id}", result.stdout)
            self.assertIn("transient_failure=1", result.stdout)
            self.assertIn("failure_found=1", result.stdout)
            self.assertIn("turn_state=completed", result.stdout)

    def test_claude_latest_normal_turn_overrides_previous_api_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "claude"
            cwd = root / "workspace"
            project = config / "projects" / "-root-workspace"
            project.mkdir(parents=True)
            cwd.mkdir()
            session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
            events = [
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(cwd),
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": f"run_id={RUN_ID}"}],
                    },
                },
                {
                    "type": "assistant",
                    "isApiErrorMessage": True,
                    "sessionId": session_id,
                    "message": {"content": [{"type": "text", "text": "429 Too Many Requests"}]},
                },
                {"type": "system", "subtype": "turn_duration", "sessionId": session_id},
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "message": {"content": [{"type": "text", "text": "finished"}]},
                },
                {"type": "system", "subtype": "turn_duration", "sessionId": session_id},
            ]
            (project / f"{session_id}.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )

            result = self._run_lookup("claude", cwd, data_dir=config)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("transient_failure=0", result.stdout)
            self.assertIn("failure_found=0", result.stdout)
            self.assertIn("turn_state=completed", result.stdout)

    def test_claude_newer_user_turn_is_in_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "claude"
            cwd = root / "workspace"
            project = config / "projects" / "-root-workspace"
            project.mkdir(parents=True)
            cwd.mkdir()
            session_id = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
            events = [
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(cwd),
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": f"run_id={RUN_ID}"}],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "message": {"content": [{"type": "text", "text": "working"}]},
                },
            ]
            (project / f"{session_id}.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )

            result = self._run_lookup("claude", cwd, data_dir=config)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("transient_failure=0", result.stdout)
            self.assertIn("failure_found=0", result.stdout)
            self.assertIn("turn_state=in_progress", result.stdout)

    def test_claude_authentication_error_is_not_transient(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "claude"
            cwd = root / "workspace"
            project = config / "projects" / "-root-workspace"
            project.mkdir(parents=True)
            cwd.mkdir()
            session_id = "99999999-8888-4777-8666-555555555555"
            events = [
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(cwd),
                    "message": {
                        "content": [{"type": "text", "text": f"run_id={RUN_ID}"}]
                    },
                },
                {
                    "type": "assistant",
                    "isApiErrorMessage": True,
                    "sessionId": session_id,
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "API Error: 401 Upstream request failed: Invalid credential",
                            }
                        ]
                    },
                },
                {"type": "system", "subtype": "turn_duration", "sessionId": session_id},
            ]
            (project / f"{session_id}.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )

            result = self._run_lookup("claude", cwd, data_dir=config)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("transient_failure=0", result.stdout)
            self.assertIn("failure_found=1", result.stdout)

    def test_opencode_v1_finds_session_and_latest_assistant_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "opencode"
            cwd = root / "workspace"
            data_dir.mkdir()
            cwd.mkdir()
            db = data_dir / "opencode.db"
            session_id = "ses_v1_upstream_error"
            with sqlite3.connect(db) as connection:
                connection.executescript(
                    """
                    CREATE TABLE session (
                        id TEXT PRIMARY KEY, directory TEXT NOT NULL,
                        time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL
                    );
                    CREATE TABLE message (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                        time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
                        data TEXT NOT NULL
                    );
                    CREATE TABLE part (
                        id TEXT PRIMARY KEY, message_id TEXT NOT NULL,
                        session_id TEXT NOT NULL, time_created INTEGER NOT NULL,
                        time_updated INTEGER NOT NULL, data TEXT NOT NULL
                    );
                    """
                )
                created = self._created_ms()
                connection.execute(
                    "INSERT INTO session VALUES (?, ?, ?, ?)",
                    (session_id, str(cwd), created, created + 5000),
                )
                user_id = "msg_v1_user"
                connection.execute(
                    "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
                    (user_id, session_id, created + 1, created + 1, '{"role":"user"}'),
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "prt_v1_user",
                        user_id,
                        session_id,
                        created + 1,
                        created + 1,
                        json.dumps({"type": "text", "text": f"run_id={RUN_ID}"}),
                    ),
                )
                connection.execute(
                    "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
                    (
                        "msg_v1_assistant",
                        session_id,
                        created + 2,
                        created + 3,
                        json.dumps(
                            {
                                "role": "assistant",
                                "error": {"name": "UnknownError", "data": {"message": TRANSIENT_TEXT}},
                            }
                        ),
                    ),
                )

            result = self._run_lookup("opencode", cwd, data_dir=data_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"session_id={session_id}", result.stdout)
            self.assertIn("transient_failure=1", result.stdout)
            self.assertIn("turn_state=completed", result.stdout)

    def test_opencode_v2_reads_session_messages_and_idle_outcome(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "opencode"
            cwd = root / "workspace"
            data_dir.mkdir()
            cwd.mkdir()
            db = data_dir / "opencode.db"
            session_id = "ses_v2_upstream_error"
            with sqlite3.connect(db) as connection:
                connection.executescript(
                    """
                    CREATE TABLE session_v2 (
                        id TEXT PRIMARY KEY, directory TEXT NOT NULL,
                        time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL
                    );
                    CREATE TABLE session_message (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                        type TEXT NOT NULL, seq INTEGER NOT NULL,
                        time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
                        data TEXT NOT NULL
                    );
                    """
                )
                created = self._created_ms()
                connection.execute(
                    "INSERT INTO session_v2 VALUES (?, ?, ?, ?)",
                    (session_id, str(cwd), created, created + 5000),
                )
                rows = [
                    ("msg_v2_user", "user", 1, json.dumps({"text": f"run_id={RUN_ID}"})),
                    (
                        "msg_v2_assistant",
                        "assistant",
                        2,
                        json.dumps({"error": {"type": "provider.error", "message": TRANSIENT_TEXT}}),
                    ),
                    ("msg_v2_idle", "idle", 3, json.dumps({"outcome": "failed"})),
                ]
                for message_id, kind, seq, data in rows:
                    connection.execute(
                        "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (message_id, session_id, kind, seq, created + seq, created + seq, data),
                    )

            result = self._run_lookup("opencode", cwd, data_dir=data_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"session_id={session_id}", result.stdout)
            self.assertIn("transient_failure=1", result.stdout)
            self.assertIn("turn_state=completed", result.stdout)

    def test_opencode_v2_streaming_assistant_is_in_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "opencode"
            cwd = root / "workspace"
            data_dir.mkdir()
            cwd.mkdir()
            db = data_dir / "opencode.db"
            session_id = "ses_v2_in_progress"
            with sqlite3.connect(db) as connection:
                connection.executescript(
                    """
                    CREATE TABLE session_v2 (
                        id TEXT PRIMARY KEY, directory TEXT NOT NULL,
                        time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL
                    );
                    CREATE TABLE session_message (
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                        type TEXT NOT NULL, seq INTEGER NOT NULL,
                        time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
                        data TEXT NOT NULL
                    );
                    """
                )
                created = self._created_ms()
                connection.execute(
                    "INSERT INTO session_v2 VALUES (?, ?, ?, ?)",
                    (session_id, str(cwd), created, created + 5000),
                )
                rows = [
                    ("msg_v2_user", "user", 1, json.dumps({"text": f"run_id={RUN_ID}"})),
                    ("msg_v2_assistant", "assistant", 2, json.dumps({"text": "working"})),
                ]
                for message_id, kind, seq, data in rows:
                    connection.execute(
                        "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (message_id, session_id, kind, seq, created + seq, created + seq, data),
                    )

            result = self._run_lookup("opencode", cwd, data_dir=data_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("transient_failure=0", result.stdout)
            self.assertIn("turn_state=in_progress", result.stdout)


if __name__ == "__main__":
    unittest.main()
