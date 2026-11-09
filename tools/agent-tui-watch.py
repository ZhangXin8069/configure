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
    parser.add_argument("--agent", choices=("codex", "claude", "opencode", "commandcode"), required=True)
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
    parser.add_argument("--idle-nudge-command-json", default="")
    parser.add_argument("--idle-nudge-markers", default="")
    parser.add_argument("--idle-seconds", type=float, default=300.0)
    parser.add_argument("--idle-min-turn-seconds", type=float, default=30.0)
    parser.add_argument("--idle-nudge-timeout", type=float, default=1800.0)
    parser.add_argument("--idle-poll", type=float, default=15.0)
    parser.add_argument("--idle-max-nudges", type=int, default=0)
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


def render_recovery_command(
    raw: str,
    state: dict[str, str],
    run_id: str,
    message: str = "",
) -> list[str] | None:
    try:
        command = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        return None
    if command[0] == "--":
        command = command[1:]
    if not command:
        return None
    values = {
        "{run_id}": run_id,
        "{session_id}": state.get("session_id", ""),
        "{thread_id}": state.get("thread_id", ""),
        "{message}": message,
    }
    rendered: list[str] = []
    for item in command:
        for placeholder, value in values.items():
            item = item.replace(placeholder, value)
        rendered.append(item)
    return rendered


def read_last_user_input(
    args: argparse.Namespace,
) -> tuple[float | None, str]:
    """Return the epoch seconds of the newest real user input, if detectable."""
    helper = Path(__file__).with_name("agent-session-state.py")
    if not helper.is_file():
        return None, "state_helper_missing"
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
        "--last-user-input",
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
        return None, "state_timeout"
    if result.returncode != 0:
        reason = result.stderr.strip().replace("\n", " ")[:120] or "state_unavailable"
        return None, reason
    value = ""
    for line in result.stdout.splitlines():
        key, separator, payload = line.partition("=")
        if separator and key == "last_user_input":
            value = payload.strip()
            break
    if not value or value == "0":
        return None, "no_user_input"
    try:
        return float(value), "ok"
    except ValueError:
        return None, "invalid_timestamp"


def write_attempt_state(
    path: str,
    last_user_input: float,
    nudged_at: float,
    count: int,
) -> None:
    if not path:
        return
    payload = {
        "last_user_input": round(last_user_input, 3),
        "nudged_at": round(nudged_at, 3),
        "count": count,
        "pid": os.getpid(),
    }
    temp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(temp, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.write("\n")
        os.replace(temp, path)
    except OSError:
        try:
            os.unlink(temp)
        except OSError:
            pass


def read_attempt_state(path: str) -> tuple[float | None, int]:
    """Load the previous nudge time/count so a watcher restart keeps the cooldown."""
    if not path:
        return None, 0
    try:
        with open(path, encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, ValueError):
        return None, 0
    if not isinstance(payload, dict):
        return None, 0
    try:
        nudged_at = float(payload.get("nudged_at") or 0)
    except (TypeError, ValueError):
        nudged_at = 0.0
    try:
        count = int(payload.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    return (nudged_at if nudged_at > 0 else None), max(0, count)


def read_nudge_markers(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path:
        return values
    enabled_file = os.path.join(path, ".idle-nudge-enabled")
    complete_file = os.path.join(path, ".goal-complete")
    attempt_file = os.path.join(path, ".idle-nudge-attempted")
    values["enabled"] = "1" if os.path.isfile(enabled_file) else "0"
    values["complete"] = "1" if os.path.isfile(complete_file) else "0"
    values["attempted"] = "1" if os.path.isfile(attempt_file) else "0"
    if values["enabled"] == "1":
        try:
            with open(enabled_file, encoding="utf-8") as stream:
                payload = json.load(stream)
            if isinstance(payload, dict):
                values["goal"] = str(payload.get("goal", ""))
        except (OSError, ValueError):
            pass
    return values


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
    if args.idle_seconds < 0 or args.idle_min_turn_seconds < 0 or args.idle_nudge_timeout <= 0:
        return "invalid_idle_timing"
    if args.idle_poll <= 0:
        return "invalid_idle_poll"
    if args.idle_max_nudges < 0:
        return "invalid_idle_max_nudges"
    if args.idle_nudge_markers and not os.path.isabs(args.idle_nudge_markers):
        return "idle_nudge_markers_not_absolute"
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
    idle_attempt_file = (
        os.path.join(args.idle_nudge_markers, ".idle-nudge-attempted")
        if args.idle_nudge_markers
        else ""
    )
    next_idle_poll = started + args.idle_poll
    idle_nudge_enabled = bool(args.idle_nudge_command_json and args.idle_nudge_markers)
    completed_since: float | None = None
    last_nudge_at, nudge_count = read_attempt_state(idle_attempt_file)
    write_log(
        args.log,
        "start",
        agent=args.agent,
        run_id=args.run_id,
        pid=args.pid,
        grace=args.grace,
        interval=args.interval,
        max_runtime=args.max_runtime,
        idle_nudge=1 if idle_nudge_enabled else 0,
        idle_seconds=args.idle_seconds,
    )
    if idle_nudge_enabled and args.idle_seconds > 0:
        append_event(
            args.event_file,
            "tui-idle-nudge-armed",
            run_id=args.run_id,
            pid=args.pid,
            idle_seconds=args.idle_seconds,
            markers=args.idle_nudge_markers,
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

        # Idle nudge: only while a completed turn is waiting and the auto skill
        # has armed the run.  Never inject during failure recovery.
        if idle_nudge_enabled and args.idle_seconds > 0 and now >= next_idle_poll:
            next_idle_poll = now + args.idle_poll
            markers = read_nudge_markers(args.idle_nudge_markers)
            turn_completed = bool(state and state.get("turn_state") == "completed")
            if turn_completed:
                if completed_since is None:
                    completed_since = now
            else:
                completed_since = None

            if failure_complete:
                write_log(args.log, "idle-skip", reason="failure_recovery", pid=args.pid)
            elif markers.get("enabled") != "1":
                write_log(args.log, "idle-skip", reason="nudge_disabled", pid=args.pid)
            elif markers.get("complete") == "1":
                write_log(args.log, "idle-skip", reason="goal_complete", pid=args.pid)
            elif not turn_completed:
                write_log(args.log, "idle-skip", reason="turn_running", pid=args.pid)
            elif completed_since is not None and now - completed_since < args.idle_min_turn_seconds:
                pass
            elif args.idle_max_nudges > 0 and nudge_count >= args.idle_max_nudges:
                if nudge_count == args.idle_max_nudges:
                    write_log(args.log, "idle-skip", reason="max_nudges", pid=args.pid, nudges=nudge_count)
                    nudge_count += 1
            else:
                last_user, user_reason = read_last_user_input(args)
                if last_user is None:
                    write_log(args.log, "idle-skip", reason=user_reason, pid=args.pid)
                else:
                    # Activity = newest real user input or our own last nudge, so a
                    # finished nudge turn cannot immediately trigger another one.
                    activity = max(last_user, last_nudge_at or 0.0)
                    idle_for = time.time() - activity
                    if idle_for < args.idle_seconds:
                        write_log(args.log, "idle-wait", pid=args.pid, idle_seconds=round(idle_for, 1))
                    else:
                        command = render_recovery_command(
                            args.idle_nudge_command_json,
                            state,
                            args.run_id,
                            "【自动续跑】请简要汇报当前阶段性工作进度到日志目录，"
                            "并继续下一轮工作或进一步拓展本轮工作；不要重复已完成工作。",
                        )
                        if not command:
                            write_log(args.log, "idle-skip", reason="idle_command_missing", pid=args.pid)
                        elif not (state.get("session_id") or state.get("thread_id")):
                            write_log(args.log, "idle-skip", reason="session_missing", pid=args.pid)
                        elif args.stop_file and Path(args.stop_file).exists():
                            write_log(args.log, "stop", reason="stop_requested", pid=args.pid)
                            return 0
                        else:
                            nudge_count += 1
                            last_nudge_at = time.time()
                            write_attempt_state(
                                idle_attempt_file,
                                last_user,
                                last_nudge_at,
                                nudge_count,
                            )
                            write_log(
                                args.log,
                                "idle-nudge",
                                reason="user_idle",
                                pid=args.pid,
                                idle_seconds=round(idle_for, 1),
                                nudges=nudge_count,
                                command=Path(command[0]).name,
                            )
                            append_event(
                                args.event_file,
                                "tui-idle-nudge-start",
                                run_id=args.run_id,
                                pid=args.pid,
                                command=Path(command[0]).name,
                                idle_seconds=round(idle_for, 1),
                                nudges=nudge_count,
                            )
                            try:
                                result = subprocess.run(
                                    command,
                                    text=True,
                                    capture_output=True,
                                    check=False,
                                    timeout=args.idle_nudge_timeout,
                                )
                            except subprocess.TimeoutExpired:
                                write_log(args.log, "idle-nudge-failed", reason="idle_timeout", pid=args.pid)
                                append_event(
                                    args.event_file,
                                    "tui-idle-nudge-end",
                                    run_id=args.run_id,
                                    pid=args.pid,
                                    status="failed",
                                    reason="idle_timeout",
                                )
                            except OSError as error:
                                write_log(
                                    args.log,
                                    "idle-nudge-failed",
                                    reason="idle_exec_error",
                                    pid=args.pid,
                                    detail=error.__class__.__name__,
                                )
                                append_event(
                                    args.event_file,
                                    "tui-idle-nudge-end",
                                    run_id=args.run_id,
                                    pid=args.pid,
                                    status="failed",
                                    reason="idle_exec_error",
                                )
                            else:
                                if result.returncode != 0:
                                    write_log(
                                        args.log,
                                        "idle-nudge-failed",
                                        reason="idle_exit",
                                        pid=args.pid,
                                        exit_code=result.returncode,
                                    )
                                    append_event(
                                        args.event_file,
                                        "tui-idle-nudge-end",
                                        run_id=args.run_id,
                                        pid=args.pid,
                                        status="failed",
                                        exit_code=result.returncode,
                                    )
                                else:
                                    write_log(args.log, "idle-nudge-ok", pid=args.pid, nudges=nudge_count)
                                    append_event(
                                        args.event_file,
                                        "tui-idle-nudge-end",
                                        run_id=args.run_id,
                                        pid=args.pid,
                                        status="ok",
                                        nudges=nudge_count,
                                    )
                                    try:
                                        record_dir = Path(args.idle_nudge_markers or ".")
                                        (record_dir / "idle-nudge-last.txt").write_text(
                                            "time=" + time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n"
                                            "command=" + json.dumps(command, ensure_ascii=False) + "\n"
                                            "returncode=" + str(result.returncode) + "\n"
                                            "stdout:\n" + (result.stdout or "")[-4000:] + "\n"
                                            "stderr:\n" + (result.stderr or "")[-4000:] + "\n",
                                            encoding="utf-8",
                                        )
                                    except OSError:
                                        pass
                            # A nudge command can run for minutes. Restart the
                            # idle clock at completion so it cannot immediately
                            # trigger another nudge based on its own start time.
                            last_nudge_at = time.time()
                            write_attempt_state(
                                idle_attempt_file,
                                last_user,
                                last_nudge_at,
                                nudge_count,
                            )

        if deadline is None:
            time.sleep(args.interval)
        else:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
