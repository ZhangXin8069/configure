#!/usr/bin/env python3
"""Idle-nudge coverage for agent-tui-watch.py."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).with_name("agent-tui-watch.py")
SESSION_STATE = Path(__file__).with_name("agent-session-state.py")
RUN_ID = "20261021T181344.idle"
CREATED_AT = "2026-10-21T18:13:44+0800"
THREAD_ID = "01a15df3-e05e-7e23-aae4-b7fefee75e46"


class IdleNudgeTests(unittest.TestCase):
    def _fixture(self, root: Path, user_age_seconds: float | None) -> tuple[Path, Path, Path]:
        codex_home = root / "codex-home"
        cwd = root / "workspace"
        run_dir = root / "run"
        sessions = codex_home / "sessions" / "2026" / "10" / "21"
        for path in (sessions, cwd, run_dir):
            path.mkdir(parents=True, exist_ok=True)
        state_db = codex_home / "state_5.sqlite"
        rollout = sessions / "rollout-idle.jsonl"
        created_ms = int(
            datetime.strptime(CREATED_AT, "%Y-%m-%dT%H:%M:%S%z").timestamp() * 1000
        )
        with sqlite3.connect(state_db) as connection:
            connection.execute(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    created_at_ms INTEGER NOT NULL,
                    cwd TEXT NOT NULL,
                    source TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    first_user_message TEXT NOT NULL DEFAULT '',
                    preview TEXT NOT NULL DEFAULT '',
                    rollout_path TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, 'cli', 0, ?, ?, ?)",
                (
                    THREAD_ID,
                    created_ms,
                    str(cwd),
                    f"run_id={RUN_ID}",
                    f"run_id={RUN_ID}",
                    str(rollout),
                ),
            )

        events = []
        if user_age_seconds is not None:
            stamp = datetime.now(timezone.utc) - timedelta(seconds=user_age_seconds)
            events.append(
                {
                    "type": "event_msg",
                    "timestamp": stamp.isoformat(),
                    "payload": {"type": "user_message", "message": f"run_id={RUN_ID}"},
                }
            )
        events.append({"type": "event_msg", "payload": {"type": "task_complete", "error": None}})
        rollout.write_text(
            "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
            encoding="utf-8",
        )
        return codex_home, cwd, run_dir

    @staticmethod
    def _child():
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    @staticmethod
    def _nudge_script(root: Path) -> tuple[Path, Path]:
        record = root / "nudges.txt"
        path = root / "nudge.py"
        path.write_text(
            "import pathlib, sys\n"
            "with pathlib.Path(sys.argv[1]).open('a', encoding='utf-8') as stream:\n"
            "    stream.write(sys.argv[2] + '\\n')\n",
            encoding="utf-8",
        )
        return path, record

    def _run(
        self,
        codex_home: Path,
        cwd: Path,
        run_dir: Path,
        child,
        *,
        nudge: Path,
        record: Path,
        idle_seconds: float,
        max_runtime: float = 2.0,
        stop_file: Path | None = None,
        prefix: list[str] | None = None,
    ):
        command = [
            sys.executable,
            str(SCRIPT),
            "--agent",
            "codex",
            "--run-id",
            RUN_ID,
            "--cwd",
            str(cwd),
            "--created-at",
            CREATED_AT,
            "--state-db",
            str(codex_home / "state_5.sqlite"),
            "--pid",
            str(child.pid),
            "--interval",
            "0.05",
            "--max-runtime",
            str(max_runtime),
            "--log",
            str(run_dir / "tui-watch.log"),
            "--idle-nudge-command-json",
            json.dumps(
                (prefix or []) + [sys.executable, str(nudge), str(record), "{message}"],
                separators=(",", ":"),
            ),
            "--idle-nudge-markers",
            str(run_dir),
            "--idle-seconds",
            str(idle_seconds),
            "--idle-poll",
            "0.05",
            "--idle-min-turn-seconds",
            "0",
            "--idle-nudge-timeout",
            "2",
            "--event-file",
            str(run_dir / "events.jsonl"),
        ]
        if stop_file is not None:
            command += ["--stop-file", str(stop_file)]
        return subprocess.run(
            command, text=True, capture_output=True, check=False, timeout=10
        )

    @staticmethod
    def _enable(run_dir: Path, goal: str = "finish the task") -> None:
        (run_dir / ".idle-nudge-enabled").write_text(
            json.dumps({"schema_version": 1, "run_id": RUN_ID, "goal": goal}) + "\n",
            encoding="utf-8",
        )

    def test_idle_turn_is_nudged_as_user_message(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=600)
            self._enable(run_dir)
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home, cwd, run_dir, child, nudge=nudge, record=record, idle_seconds=60
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
                message = record.read_text(encoding="utf-8")
                self.assertIn("简要汇报当前阶段性工作进度到日志目录", message)
                self.assertIn("继续下一轮工作或进一步拓展本轮工作", message)
                log_text = (run_dir / "tui-watch.log").read_text(encoding="utf-8")
                self.assertIn("action=idle-nudge", log_text)
                self.assertIn("action=idle-nudge-ok", log_text)
                events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
                self.assertIn("tui-idle-nudge-start", events)
                self.assertIn("tui-idle-nudge-end", events)
                last = (run_dir / "idle-nudge-last.txt").read_text(encoding="utf-8")
                self.assertIn("returncode=0", last)
                self.assertIn("自动续跑", last)
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_leading_separator_is_stripped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=600)
            self._enable(run_dir)
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home,
                    cwd,
                    run_dir,
                    child,
                    nudge=nudge,
                    record=record,
                    idle_seconds=60,
                    prefix=["--"],
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
                self.assertTrue(record.exists())
                log_text = (run_dir / "tui-watch.log").read_text(encoding="utf-8")
                self.assertIn("action=idle-nudge-ok", log_text)
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_recent_user_input_does_not_nudge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=5)
            self._enable(run_dir)
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home, cwd, run_dir, child, nudge=nudge, record=record, idle_seconds=300
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertFalse(record.exists())
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_completed_goal_blocks_nudge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=600)
            self._enable(run_dir)
            (run_dir / ".goal-complete").write_text("{}\n", encoding="utf-8")
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home, cwd, run_dir, child, nudge=nudge, record=record, idle_seconds=60
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertFalse(record.exists())
                log_text = (run_dir / "tui-watch.log").read_text(encoding="utf-8")
                self.assertIn("reason=goal_complete", log_text)
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_disabled_marker_blocks_nudge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=600)
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home, cwd, run_dir, child, nudge=nudge, record=record, idle_seconds=60
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertFalse(record.exists())
                log_text = (run_dir / "tui-watch.log").read_text(encoding="utf-8")
                self.assertIn("reason=nudge_disabled", log_text)
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_nudge_respects_stop_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=600)
            self._enable(run_dir)
            stop_file = run_dir / "stop"
            stop_file.touch()
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home,
                    cwd,
                    run_dir,
                    child,
                    nudge=nudge,
                    record=record,
                    idle_seconds=60,
                    stop_file=stop_file,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(record.exists())
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_nudge_repeats_only_after_idle_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, run_dir = self._fixture(root, user_age_seconds=600)
            self._enable(run_dir)
            nudge, record = self._nudge_script(root)
            child = self._child()
            try:
                result = self._run(
                    codex_home,
                    cwd,
                    run_dir,
                    child,
                    nudge=nudge,
                    record=record,
                    idle_seconds=0.2,
                    max_runtime=1.2,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertGreaterEqual(len(record.read_text(encoding="utf-8").splitlines()), 2)
                state = json.loads((run_dir / ".idle-nudge-attempted").read_text(encoding="utf-8"))
                self.assertGreaterEqual(state["count"], 2)
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_session_state_reports_last_user_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, _run_dir = self._fixture(root, user_age_seconds=42)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SESSION_STATE),
                    "--agent",
                    "codex",
                    "--run-id",
                    RUN_ID,
                    "--cwd",
                    str(cwd),
                    "--created-at",
                    CREATED_AT,
                    "--state-db",
                    str(codex_home / "state_5.sqlite"),
                    "--last-user-input",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = result.stdout.strip().split("=", 1)[1]
            age = time.time() - float(value)
            self.assertGreater(age, 30)
            self.assertLess(age, 120)


if __name__ == "__main__":
    unittest.main()
