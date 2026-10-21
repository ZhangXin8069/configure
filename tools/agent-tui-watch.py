#!/usr/bin/env python3
"""Resume a live TUI task after its latest turn ended in an unexpected failure."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DEFAULT_SCAN_BYTES = 2 * 1024 * 1024


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch a live agent TUI for a completed failed turn."
    )
    parser.add_argument("--agent", choices=("codex", "claude", "opencode"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--created-at", default="")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--state-db", default="")
    parser.add_argument("--stop-file", default="")
    parser.add_argument("--scan-bytes", type=int, default=DEFAULT_SCAN_BYTES)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--grace", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--max-runtime", type=float, default=0.0)
    parser.add_argument("--heartbeat", type=float, default=60.0)
    parser.add_argument("--state-timeout", type=float, default=5.0)
    parser.add_argument("--recover-timeout", type=float, default=1800.0)
    parser.add_argument("--recover-command-json", default="")
    parser.add_argument("--attempt-marker", default="")
    parser.add_argument("--event-file", default="")
    parser.add_argument("--log", default="")
    return parser.parse_args(argv)


def write_log(path: str, action: str, **fields: Any) -> None:
    if not path:
        return
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    values = {"time": timestamp, "source": "agent-tui-watch", "action": action}
    values.update(fields)
    line = " ".join(f"{key}={clean_value(value)}" for key, value in values.items())
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    except OSError:
        pass


def clean_value(value: Any) -> str:
    return str(value).replace("\r", "_").replace("\n", "_").replace(" ", "_")


def process_identity(pid: int) -> tuple[bool, str]:
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        data = proc_stat.read_text(encoding="utf-8")
        fields = data[data.rfind(")") + 2 :].split()
        if len(fields) < 20:
            return True, ""
        if fields[0] == "Z":
            return False, ""
        return True, fields[19]
    except FileNotFoundError:
        return False, ""
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            text=True,
            capture_output=True,
            check=False,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return True, result.stdout.strip()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False, ""
    except PermissionError:
        return True, ""
    return True, ""


def read_session_state(args: argparse.Namespace) -> dict[str, str] | None:
    helper = Path(__file__).with_name("agent-session-state.py")
    if not helper.is_file():
        return None
    command = [
        sys.executable,
        str(helper),
        "--agent",
        args.agent,
        "--run-id",
        args.run_id,
        "--cwd",
        args.cwd,
        "--scan-bytes",
        str(args.scan_bytes),
    ]
    if args.created_at:
        command += ["--created-at", args.created_at]
    if args.data_dir:
        command += ["--data-dir", args.data_dir]
    if args.state_db:
        command += ["--state-db", args.state_db]
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.state_timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def append_event(path: str, event: str, **fields: Any) -> None:
    if not path:
        return
    payload = {
        "schema_version": "1",
        "event": event,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "agent-tui-watch",
    }
    payload.update(fields)
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def state_fingerprint(state: dict[str, str]) -> str:
    state_path = state.get("state_path", "")
    if state_path:
        try:
            info = os.stat(state_path)
            return f"{state_path}:{info.st_mtime_ns}:{info.st_size}"
        except OSError:
            pass
    keys = ("state_path", "thread_id", "session_id", "turn_state", "failure_found")
    return "|".join(f"{key}={state.get(key, '')}" for key in keys)


def claim_recovery(marker: str, fingerprint: str, retry_after: float) -> bool:
    if not marker:
        return True
    lock_path = f"{marker}.lock"
    try:
        lock_descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            if time.time() - os.stat(lock_path).st_mtime > max(60.0, retry_after * 2):
                os.unlink(lock_path)
                lock_descriptor = os.open(
                    lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
            else:
                return False
        except (FileExistsError, OSError):
            return False
    except OSError:
        return False
    try:
        claimed_at = 0.0
        claimed_fingerprint = ""
        try:
            payload = json.loads(Path(marker).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                claimed_at = float(payload.get("claimed_at", 0))
                claimed_fingerprint = str(payload.get("fingerprint", ""))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        if claimed_fingerprint == fingerprint and time.time() - claimed_at < retry_after:
            return False
        payload = {
            "fingerprint": fingerprint,
            "claimed_at": time.time(),
            "claimed_at_iso": datetime.now().astimezone().isoformat(timespec="seconds"),
            "pid": os.getpid(),
        }
        Path(marker).write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        os.close(lock_descriptor)
        try:
            os.unlink(lock_path)
        except OSError:
            pass


def render_recovery_command(raw: str, state: dict[str, str], run_id: str) -> list[str] | None:
    try:
        command = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        return None
    values = {
        "{run_id}": run_id,
        "{session_id}": state.get("session_id", ""),
        "{thread_id}": state.get("thread_id", ""),
    }
    rendered: list[str] = []
    for item in command:
        for placeholder, value in values.items():
            item = item.replace(placeholder, value)
        rendered.append(item)
    return rendered


def validate_args(args: argparse.Namespace) -> str:
    if not RUN_ID_RE.fullmatch(args.run_id):
        return "invalid_run_id"
    if not os.path.isabs(args.cwd):
        return "cwd_not_absolute"
    if args.stop_file and not os.path.isabs(args.stop_file):
        return "stop_file_not_absolute"
    if args.pid <= 0:
        return "invalid_pid"
    if args.scan_bytes <= 0:
        return "invalid_scan_bytes"
    if args.grace < 0 or args.interval <= 0 or args.max_runtime < 0 or args.heartbeat <= 0:
        return "invalid_timing"
    if args.state_timeout <= 0 or args.recover_timeout <= 0:
        return "invalid_timeout"
    return ""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    invalid_reason = validate_args(args)
    if invalid_reason:
        print(f"status=invalid reason={invalid_reason}", file=sys.stderr)
        return 2

    if args.stop_file and Path(args.stop_file).exists():
        write_log(args.log, "stop", reason="stop_requested", pid=args.pid)
        return 0

    alive, identity = process_identity(args.pid)
    if not alive:
        write_log(args.log, "stop", reason="process_not_alive", pid=args.pid)
        return 0

    started = time.monotonic()
    deadline = started + args.max_runtime if args.max_runtime > 0 else None
    next_heartbeat = started + args.heartbeat
    pending_since: float | None = None
    write_log(
        args.log,
        "start",
        agent=args.agent,
        run_id=args.run_id,
        pid=args.pid,
        grace=args.grace,
        interval=args.interval,
        max_runtime=args.max_runtime,
    )

    while True:
        now = time.monotonic()
        if args.stop_file and Path(args.stop_file).exists():
            write_log(args.log, "stop", reason="stop_requested", pid=args.pid)
            return 0
        if deadline is not None and now >= deadline:
            write_log(args.log, "stop", reason="max_runtime", pid=args.pid)
            return 3

        alive, current_identity = process_identity(args.pid)
        if not alive or (identity and current_identity and current_identity != identity):
            write_log(args.log, "stop", reason="process_exited", pid=args.pid)
            return 0

        if now >= next_heartbeat:
            write_log(args.log, "heartbeat", pid=args.pid, elapsed=round(now - started, 1))
            next_heartbeat = now + args.heartbeat

        state = read_session_state(args)
        failure_complete = bool(
            state
            and state.get("turn_state") == "completed"
            and state.get("failure_found") == "1"
        )
        if failure_complete:
            if pending_since is None:
                pending_since = now
                write_log(args.log, "detected", reason="completed_failed_turn", pid=args.pid)
            if now - pending_since >= args.grace:
                alive, current_identity = process_identity(args.pid)
                if not alive or (identity and current_identity and current_identity != identity):
                    write_log(args.log, "stop", reason="process_exited", pid=args.pid)
                    return 0
                confirm = read_session_state(args)
                if not (
                    confirm
                    and confirm.get("turn_state") == "completed"
                    and confirm.get("failure_found") == "1"
                ):
                    write_log(args.log, "skip", reason="turn_changed", pid=args.pid)
                    pending_since = None
                else:
                    if args.stop_file and Path(args.stop_file).exists():
                        write_log(args.log, "stop", reason="stop_requested", pid=args.pid)
                        return 0
                    command = render_recovery_command(args.recover_command_json, confirm, args.run_id)
                    if not command:
                        write_log(args.log, "skip", reason="recover_command_missing", pid=args.pid)
                        return 3
                    fingerprint = state_fingerprint(confirm)
                    if not claim_recovery(args.attempt_marker, fingerprint, max(args.grace, 0.05)):
                        write_log(args.log, "skip", reason="recovery_in_progress", pid=args.pid)
                        return 4
                    write_log(
                        args.log,
                        "resume",
                        reason="completed_failed_turn",
                        pid=args.pid,
                        command=Path(command[0]).name,
                    )
                    append_event(
                        args.event_file,
                        "tui-resume-start",
                        run_id=args.run_id,
                        pid=args.pid,
                        command=Path(command[0]).name,
                    )
                    try:
                        result = subprocess.run(
                            command,
                            text=True,
                            capture_output=True,
                            check=False,
                            timeout=args.recover_timeout,
                        )
                    except subprocess.TimeoutExpired:
                        write_log(args.log, "resume-failed", reason="recover_timeout", pid=args.pid)
                        append_event(
                            args.event_file,
                            "tui-resume-end",
                            run_id=args.run_id,
                            pid=args.pid,
                            status="failed",
                            reason="recover_timeout",
                        )
                        pending_since = None
                        continue
                    except OSError as error:
                        write_log(
                            args.log,
                            "resume-failed",
                            reason="recover_exec_error",
                            pid=args.pid,
                            detail=error.__class__.__name__,
                        )
                        append_event(
                            args.event_file,
                            "tui-resume-end",
                            run_id=args.run_id,
                            pid=args.pid,
                            status="failed",
                            reason="recover_exec_error",
                        )
                        pending_since = None
                        continue
                    if result.returncode != 0:
                        write_log(
                            args.log,
                            "resume-failed",
                            reason="recover_exit",
                            pid=args.pid,
                            exit_code=result.returncode,
                        )
                        append_event(
                            args.event_file,
                            "tui-resume-end",
                            run_id=args.run_id,
                            pid=args.pid,
                            status="failed",
                            exit_code=result.returncode,
                        )
                        pending_since = None
                        continue
                    write_log(args.log, "resume-ok", pid=args.pid)
                    append_event(
                        args.event_file,
                        "tui-resume-end",
                        run_id=args.run_id,
                        pid=args.pid,
                        status="ok",
                    )
                    pending_since = None
        else:
            pending_since = None

        if deadline is None:
            time.sleep(args.interval)
        else:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
