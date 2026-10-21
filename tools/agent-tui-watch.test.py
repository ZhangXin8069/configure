#!/usr/bin/env python3

import json
import os
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).with_name("agent-tui-watch.py")
RUN_ID = "20261021T181344.watch"
CREATED_AT = "2026-10-21T18:13:44+0800"


class TuiWatchTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        codex_home = root / "codex-home"
        cwd = root / "workspace"
        sessions = codex_home / "sessions" / "2026" / "10" / "21"
        sessions.mkdir(parents=True)
        cwd.mkdir()
        state_db = codex_home / "state_5.sqlite"
        rollout = sessions / "rollout-watch.jsonl"
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
                    "01a15df3-e05e-7e23-aae4-b7fefee75e45",
                    created_ms,
                    str(cwd),
                    f"run_id={RUN_ID}",
                    f"run_id={RUN_ID}",
                    str(rollout),
                ),
            )
        return codex_home, cwd, rollout

    @staticmethod
    def _write_events(path: Path, events: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
            encoding="utf-8",
        )

    @staticmethod
    def _child() -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    @staticmethod
    def _recovery_script(root: Path) -> Path:
        path = root / "recover.py"
        path.write_text(
            "import json, pathlib, sys\n"
            "with pathlib.Path(sys.argv[1]).open('a', encoding='utf-8') as stream:\n"
            "    stream.write(sys.argv[2] + '\\n')\n"
            "if len(sys.argv) > 4:\n"
            "    mode = sys.argv[4]\n"
            "    error = None if mode == 'success' else {'message': 'Concurrency limit reached'}\n"
            "    event = {'type': 'event_msg', 'payload': {'type': 'task_complete', 'error': error}}\n"
            "    with pathlib.Path(sys.argv[3]).open('a', encoding='utf-8') as stream:\n"
            "        stream.write(json.dumps(event, separators=(',', ':')) + '\\n')\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _failing_recovery_script(root: Path) -> Path:
        path = root / "fail-recover.py"
        path.write_text(
            "import pathlib, sys\n"
            "with pathlib.Path(sys.argv[1]).open('a', encoding='utf-8') as stream:\n"
            "    stream.write('failed-attempt\\n')\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        return path

    def _run_watch(
        self,
        codex_home: Path,
        cwd: Path,
        child: subprocess.Popen,
        log: Path,
        *,
        max_runtime: float = 3,
        grace: float = 0.1,
        recovery: Path | None = None,
        recovered: Path | None = None,
        follow_up_mode: str = "success",
        stop_file: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
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
                "--grace",
                str(grace),
                "--interval",
                "0.05",
                "--max-runtime",
                str(max_runtime),
                "--log",
                str(log),
            ]
        if stop_file is not None:
            command += ["--stop-file", str(stop_file)]
        if recovery is not None and recovered is not None:
            recovery_command = json.dumps(
                [
                    sys.executable,
                    str(recovery),
                    str(recovered),
                    "{thread_id}",
                    str(cwd.parent / "codex-home" / "sessions" / "2026" / "10" / "21" / "rollout-watch.jsonl"),
                    follow_up_mode,
                ],
                separators=(",", ":"),
            )
            command += [
                "--recover-command-json",
                recovery_command,
                "--attempt-marker",
                str(log.parent / ".auto-resume-attempted"),
            ]
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )

    def test_resumes_without_stopping_live_process_after_transient_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "429 Too Many Requests"},
                        },
                    }
                ],
            )
            child = self._child()
            recovery = self._recovery_script(root)
            recovered = root / "recovered.txt"
            try:
                result = self._run_watch(
                    codex_home,
                    cwd,
                    child,
                    root / "watch.log",
                    recovery=recovery,
                    recovered=recovered,
                    max_runtime=1,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
                self.assertEqual(
                    recovered.read_text(encoding="utf-8"),
                    "01a15df3-e05e-7e23-aae4-b7fefee75e45\n",
                )
                log_text = (root / "watch.log").read_text(encoding="utf-8")
                self.assertIn("action=resume-ok", log_text)
                self.assertTrue((root / ".auto-resume-attempted").is_file())
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=2)

    def test_does_not_terminate_while_new_turn_is_progressing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "429 Too Many Requests"},
                        },
                    },
                    {"type": "event_msg", "payload": {"type": "task_started"}},
                ],
            )
            child = self._child()
            try:
                result = self._run_watch(
                    codex_home, cwd, child, root / "watch.log", max_runtime=0.6
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_stop_file_disables_tui_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "Concurrency limit reached"},
                        },
                    }
                ],
            )
            child = self._child()
            recovery = self._recovery_script(root)
            recovered = root / "recovered.txt"
            stop_file = root / "stop"
            stop_file.touch()
            try:
                result = self._run_watch(
                    codex_home,
                    cwd,
                    child,
                    root / "watch.log",
                    max_runtime=0.5,
                    recovery=recovery,
                    recovered=recovered,
                    stop_file=stop_file,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(recovered.exists())
                self.assertIn("reason=stop_requested", (root / "watch.log").read_text(encoding="utf-8"))
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_resumes_permanent_error_until_the_turn_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "401 Unauthorized"},
                        },
                    }
                ],
            )
            child = self._child()
            recovery = self._recovery_script(root)
            recovered = root / "recovered.txt"
            try:
                result = self._run_watch(
                    codex_home,
                    cwd,
                    child,
                    root / "watch.log",
                    max_runtime=1,
                    recovery=recovery,
                    recovered=recovered,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
                self.assertEqual(
                    recovered.read_text(encoding="utf-8"),
                    "01a15df3-e05e-7e23-aae4-b7fefee75e45\n",
                )
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_reaps_repeated_failures_until_watch_runtime_ends(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "Concurrency limit reached"},
                        },
                    }
                ],
            )
            child = self._child()
            recovery = self._recovery_script(root)
            recovered = root / "recovered.txt"
            try:
                result = self._run_watch(
                    codex_home,
                    cwd,
                    child,
                    root / "watch.log",
                    max_runtime=0.8,
                    grace=0.05,
                    recovery=recovery,
                    recovered=recovered,
                    follow_up_mode="failure",
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
                self.assertGreaterEqual(
                    len(recovered.read_text(encoding="utf-8").splitlines()), 2
                )
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_retries_recovery_command_failures_without_state_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "Concurrency limit reached"},
                        },
                    }
                ],
            )
            child = self._child()
            recovery = self._failing_recovery_script(root)
            recovered = root / "recovered.txt"
            try:
                result = self._run_watch(
                    codex_home,
                    cwd,
                    child,
                    root / "watch.log",
                    max_runtime=0.7,
                    grace=0.05,
                    recovery=recovery,
                    recovered=recovered,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIsNone(child.poll())
                self.assertGreaterEqual(
                    len(recovered.read_text(encoding="utf-8").splitlines()), 2
                )
            finally:
                child.terminate()
                child.wait(timeout=2)

    def test_default_grace_is_ten_seconds(self):
        namespace = runpy.run_path(str(SCRIPT), run_name="agent_tui_watch_test")
        args = namespace["parse_args"](
            [
                "--agent",
                "codex",
                "--run-id",
                RUN_ID,
                "--cwd",
                "/tmp",
                "--pid",
                str(os.getpid()),
            ]
        )
        self.assertEqual(args.grace, 10.0)

    def test_runtime_helper_watches_foreground_tui_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "429 Too Many Requests"},
                        },
                    }
                ],
            )
            run_dir = root / "run"
            run_dir.mkdir()
            log = run_dir / "tui-watch.log"
            recovery = self._recovery_script(root)
            recovered = root / "runtime-recovered.txt"
            recovery_command = json.dumps(
                [
                    sys.executable,
                    str(recovery),
                    str(recovered),
                    "{thread_id}",
                    str(rollout),
                    "success",
                ],
                separators=(",", ":"),
            )
            env = dict(os.environ)
            env.update(
                {
                    "AGENT_CONFIGURE_ROOT": str(Path(__file__).resolve().parents[1]),
                    "AGENT_RUN_ID": RUN_ID,
                    "AGENT_RUN_DIR": str(run_dir),
                    "AGENT_WORKDIR": str(cwd),
                    "AGENT_CREATED_AT": CREATED_AT,
                    "AGENT_CODEX_STATE_DB": str(codex_home / "state_5.sqlite"),
                    "AGENT_TUI_WATCH_GRACE": "0",
                    "AGENT_TUI_WATCH_INTERVAL": "0.05",
                    "AGENT_TUI_WATCH_MAX_RUNTIME": "3",
                    "AGENT_TUI_WATCH_HEARTBEAT": "10",
                    "AGENT_TUI_WATCH_STATE_TIMEOUT": "2",
                    "AGENT_TUI_WATCH_RECOVER_TIMEOUT": "2",
                }
            )
            runtime = Path(__file__).with_name("..") / "bin" / "agent-runtime.sh"
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; shift; _agent_runtime_run_tui_watched codex "$1" "${@:2}"',
                    "_",
                    str(runtime),
                    recovery_command,
                    sys.executable,
                    "-c",
                    "import time; time.sleep(1.5)",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                recovered.read_text(encoding="utf-8"),
                "01a15df3-e05e-7e23-aae4-b7fefee75e45\n",
            )
            self.assertIn("action=resume-ok", log.read_text(encoding="utf-8"))

    def test_runtime_helper_passes_stop_file_to_watcher(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, cwd, rollout = self._fixture(root)
            self._write_events(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "Concurrency limit reached"},
                        },
                    }
                ],
            )
            run_dir = root / "run"
            run_dir.mkdir()
            stop_file = run_dir / "stop"
            stop_file.touch()
            log = run_dir / "tui-watch.log"
            recovery = self._recovery_script(root)
            recovered = root / "runtime-recovered.txt"
            recovery_command = json.dumps(
                [sys.executable, str(recovery), str(recovered), "{thread_id}"],
                separators=(",", ":"),
            )
            env = dict(os.environ)
            env.update(
                {
                    "AGENT_CONFIGURE_ROOT": str(Path(__file__).resolve().parents[1]),
                    "AGENT_RUN_ID": RUN_ID,
                    "AGENT_RUN_DIR": str(run_dir),
                    "AGENT_WORKDIR": str(cwd),
                    "AGENT_CREATED_AT": CREATED_AT,
                    "AGENT_CODEX_STATE_DB": str(codex_home / "state_5.sqlite"),
                    "AGENT_STOP_FILE": str(stop_file),
                    "AGENT_TUI_WATCH_GRACE": "0",
                    "AGENT_TUI_WATCH_INTERVAL": "0.05",
                    "AGENT_TUI_WATCH_MAX_RUNTIME": "2",
                    "AGENT_TUI_WATCH_HEARTBEAT": "10",
                    "AGENT_TUI_WATCH_STATE_TIMEOUT": "2",
                    "AGENT_TUI_WATCH_RECOVER_TIMEOUT": "2",
                }
            )
            runtime = Path(__file__).with_name("..") / "bin" / "agent-runtime.sh"
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; shift; _agent_runtime_run_tui_watched codex "$1" "${@:2}"',
                    "_",
                    str(runtime),
                    recovery_command,
                    sys.executable,
                    "-c",
                    "import time; time.sleep(0.5)",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(recovered.exists())
            self.assertIn("reason=stop_requested", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
