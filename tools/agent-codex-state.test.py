#!/usr/bin/env python3

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT = Path(__file__).with_name("agent-codex-state.py")
RUN_ID = "20261021T031022.tui429"
CREATED_AT = "2026-10-21T03:10:22+0800"


class CodexStateLookupTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        codex_home = root / "codex-home"
        workspace = root / "workspace"
        sessions = codex_home / "sessions" / "2026" / "10" / "21"
        sessions.mkdir(parents=True)
        workspace.mkdir()
        state_db = codex_home / "state_5.sqlite"
        rollout = sessions / "rollout-test-tui429.jsonl"

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
        return codex_home, workspace, rollout

    def _insert_thread(
        self,
        codex_home: Path,
        workspace: Path,
        rollout: Path,
        *,
        thread_id: str = "01a15e3f-e541-7c00-b8d3-4bd9643fd6f3",
        cwd: Path | None = None,
        run_id: str = RUN_ID,
        archived: int = 0,
    ) -> None:
        created = datetime.strptime(CREATED_AT, "%Y-%m-%dT%H:%M:%S%z")
        created_ms = int(created.timestamp() * 1000)
        with sqlite3.connect(codex_home / "state_5.sqlite") as connection:
            connection.execute(
                """
                INSERT INTO threads (
                    id, created_at_ms, cwd, source, archived,
                    first_user_message, preview, rollout_path
                ) VALUES (?, ?, ?, 'cli', ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    created_ms,
                    str(cwd or workspace),
                    archived,
                    f"runtime contract\nrun_id={run_id}\n",
                    f"runtime contract\nrun_id={run_id}\n",
                    str(rollout),
                ),
            )

    @staticmethod
    def _write_rollout(path: Path, events: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
            encoding="utf-8",
        )

    def _run_lookup(self, codex_home: Path, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--run-id",
                RUN_ID,
                "--cwd",
                str(workspace),
                "--created-at",
                CREATED_AT,
                "--state-db",
                str(codex_home / "state_5.sqlite"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_finds_thread_and_reports_latest_transient_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, rollout = self._fixture(root)
            self._insert_thread(codex_home, workspace, rollout)
            self._write_rollout(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {
                                "message": "exceeded retry limit, last status: 429 Too Many Requests",
                                "codex_error_info": {
                                    "response_too_many_failed_attempts": {
                                        "http_status_code": 429
                                    }
                                },
                            },
                        },
                    }
                ],
            )

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("thread_id=01a15e3f-e541-7c00-b8d3-4bd9643fd6f3", result.stdout)
            self.assertIn(f"rollout_path={rollout}", result.stdout)
            self.assertIn("transient_failure=1", result.stdout)
            self.assertIn("turn_state=completed", result.stdout)

    def test_latest_normal_completion_overrides_earlier_transient_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, rollout = self._fixture(root)
            self._insert_thread(codex_home, workspace, rollout)
            self._write_rollout(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": "429 Too Many Requests"},
                        },
                    },
                    {
                        "type": "event_msg",
                        "payload": {"type": "task_complete", "error": None},
                    },
                ],
            )

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("transient_failure=0", result.stdout)
            self.assertIn("turn_state=completed", result.stdout)

    def test_newer_started_turn_is_reported_as_in_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, rollout = self._fixture(root)
            self._insert_thread(codex_home, workspace, rollout)
            self._write_rollout(
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

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("turn_state=in_progress", result.stdout)

    def test_nested_upstream_reasoning_error_is_resumable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, rollout = self._fixture(root)
            self._insert_thread(codex_home, workspace, rollout)
            nested_message = json.dumps(
                {
                    "error": {
                        "param": None,
                        "type": "invalid_request_error",
                        "code": "invalid_request_error",
                        "message": (
                            "Upstream request failed: [invalid_request_error] "
                            "The `reasoning_content` in the thinking mode must be passed back to the API."
                        ),
                    },
                    "type": "upstream_error",
                }
            )
            self._write_rollout(
                rollout,
                [
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "error": {"message": nested_message},
                        },
                    }
                ],
            )

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("transient_failure=1", result.stdout)

    def test_missing_exact_run_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, rollout = self._fixture(root)
            self._insert_thread(codex_home, workspace, rollout, run_id="another-run")
            self._write_rollout(
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

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 3)
            self.assertEqual(result.stdout, "")

    def test_archived_or_outside_rollout_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, _rollout = self._fixture(root)
            outside = root / "outside.jsonl"
            self._write_rollout(
                outside,
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
            self._insert_thread(codex_home, workspace, outside)

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 3)

    def test_uses_bounded_created_at_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home, workspace, rollout = self._fixture(root)
            self._insert_thread(codex_home, workspace, rollout)
            created = datetime.strptime(CREATED_AT, "%Y-%m-%dT%H:%M:%S%z")
            shifted = created + timedelta(hours=2)
            with sqlite3.connect(codex_home / "state_5.sqlite") as connection:
                connection.execute(
                    "UPDATE threads SET created_at_ms = ?",
                    (int(shifted.timestamp() * 1000),),
                )

            result = self._run_lookup(codex_home, workspace)

            self.assertEqual(result.returncode, 3)


if __name__ == "__main__":
    unittest.main()
