#!/usr/bin/env python3
"""Read-only local session lookup for Codex, Claude Code, and OpenCode."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
THREAD_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
TRANSIENT_RE = re.compile(
    r"exceeded retry limit|429\s+too many requests|too many requests|rate limit|"
    r"concurr(?:ency|ent)(?:[\s_.-]*(?:request|session|job|task|run|connection)s?)?"
    r"[\s_.-]*(?:limit|cap|quota|exceeded|reached)|"
    r"too many concurrent(?:[\s_.-]+(?:request|session|job|task|run|connection)s?)?|"
    r"maximum concurrent(?:[\s_.-]+(?:request|session|job|task|run|connection)s?)?|"
    r"parallel(?:ism)?[\s_.-]*(?:request|session|job|task|run|connection)?s?"
    r"[\s_.-]*(?:limit|cap|quota|exceeded|reached)|"
    r"并发[^\n]{0,20}(?:上限|限制|超限|已满|过多)|"
    r"overloaded_error|service unavailable|bad gateway|gateway timeout|"
    r"connection reset by peer|connection refused|stream disconnected|unexpected eof|"
    r"timed out|temporarily unavailable|upstream_error|"
    r"reasoning_content[\s\S]{0,200}passed back|"
    r"(?:http|status(?:[\s_.-]*code)?)[^0-9]*(429|500|502|503|504)",
    re.IGNORECASE | re.DOTALL,
)
TRANSIENT_ERROR_KEYS = {
    "response_too_many_failed_attempts",
    "responseTooManyFailedAttempts",
    "concurrency_limit_exceeded",
    "concurrencyLimitExceeded",
    "rate_limit_exceeded",
    "rateLimitExceeded",
    "server_overloaded",
    "serverOverloaded",
    "response_stream_connection_failed",
    "responseStreamConnectionFailed",
    "response_stream_disconnected",
    "responseStreamDisconnected",
}
DEFAULT_SCAN_BYTES = 32 * 1024 * 1024
CREATED_AT_WINDOW = timedelta(minutes=10)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only local session lookup by the configure run id."
    )
    parser.add_argument("--agent", choices=("codex", "claude", "opencode"), default="codex")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--created-at", default="")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--state-db", default="")
    parser.add_argument("--scan-bytes", type=int, default=DEFAULT_SCAN_BYTES)
    return parser.parse_args(argv)


def parse_created_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def resolve_codex_data_dir(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    codex_home = os.environ.get("CODEX_HOME", "")
    return Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"


def resolve_codex_state_db(explicit_db: str, explicit_dir: str) -> Path | None:
    override = explicit_db or os.environ.get("AGENT_CODEX_STATE_DB", "")
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_file() else None

    home = resolve_codex_data_dir(explicit_dir)
    candidates: list[tuple[int, Path]] = []
    for candidate in home.glob("state_*.sqlite"):
        if not candidate.is_file():
            continue
        match = re.search(r"state_(\d+)\.sqlite$", candidate.name)
        if match:
            candidates.append((int(match.group(1)), candidate))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def resolve_claude_data_dir(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    configured = os.environ.get("AGENT_CLAUDE_CONFIG_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def resolve_opencode_data_dir(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    configured = os.environ.get("AGENT_OPENCODE_DATA_DIR") or os.environ.get("OPENCODE_DATA_HOME")
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share") / "opencode"


def resolve_opencode_state_db(explicit_db: str, explicit_dir: str) -> Path | None:
    override = explicit_db or os.environ.get("AGENT_OPENCODE_STATE_DB", "")
    candidate = Path(override).expanduser() if override else resolve_opencode_data_dir(explicit_dir) / "opencode.db"
    return candidate if candidate.is_file() else None


def path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def table_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in connection.execute("PRAGMA table_info(threads)")}


def query_candidates(
    connection: sqlite3.Connection,
    run_id: str,
    cwd: str,
    created_at: datetime | None,
) -> list[dict[str, Any]]:
    columns = table_columns(connection)
    required = {"id", "cwd", "rollout_path", "archived"}
    if not required.issubset(columns):
        return []

    selected = ["id", "cwd", "rollout_path", "archived"]
    for optional in ("created_at_ms", "created_at", "source", "first_user_message", "preview"):
        if optional in columns:
            selected.append(optional)

    where = ["archived = 0", "cwd = ?"]
    params: list[Any] = [cwd]
    if created_at is not None and "created_at_ms" in columns:
        start = int((created_at - CREATED_AT_WINDOW).timestamp() * 1000)
        end = int((created_at + CREATED_AT_WINDOW).timestamp() * 1000)
        where.extend(["created_at_ms IS NOT NULL", "created_at_ms BETWEEN ? AND ?"])
        params.extend([start, end])
    elif created_at is not None and "created_at" in columns:
        start = int((created_at - CREATED_AT_WINDOW).timestamp())
        end = int((created_at + CREATED_AT_WINDOW).timestamp())
        where.extend(["created_at IS NOT NULL", "created_at BETWEEN ? AND ?"])
        params.extend([start, end])

    sql = f"SELECT {', '.join(selected)} FROM threads WHERE {' AND '.join(where)}"
    rows = connection.execute(sql, params).fetchall()
    marker = f"run_id={run_id}"
    candidates: list[dict[str, Any]] = []
    for row in rows:
        record = dict(zip(selected, row))
        text = "\n".join(
            str(record.get(key) or "") for key in ("first_user_message", "preview")
        )
        if marker not in text:
            continue
        record["distance_ms"] = abs(
            int(record.get("created_at_ms") or int(record.get("created_at") or 0) * 1000)
            - int(created_at.timestamp() * 1000)
        ) if created_at is not None else 0
        candidates.append(record)
    candidates.sort(key=lambda item: int(item["distance_ms"]))
    return candidates


def iter_reverse_lines(path: Path, max_bytes: int) -> Iterator[str]:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        end = stream.tell()
        start = max(0, end - max_bytes)
        stream.seek(start)
        data = stream.read(end - start)
    lines = data.splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    for raw in reversed(lines):
        yield raw.decode("utf-8", errors="replace")


def error_is_transient(error: Any, depth: int = 0) -> bool:
    if not error or depth > 8:
        return False
    if isinstance(error, str):
        return bool(TRANSIENT_RE.search(error))
    if isinstance(error, list):
        return any(error_is_transient(item, depth + 1) for item in error)
    if not isinstance(error, dict):
        return False
    if any(key in error for key in TRANSIENT_ERROR_KEYS):
        return True
    status = error.get("http_status_code", error.get("httpStatusCode", error.get("status")))
    try:
        if int(status) in (429, 500, 502, 503, 504):
            return True
    except (TypeError, ValueError):
        pass
    for key, value in error.items():
        if key in TRANSIENT_ERROR_KEYS:
            return True
        if isinstance(value, dict):
            status = value.get("http_status_code", value.get("httpStatusCode"))
            if status in (429, 500, 502, 503, 504):
                return True
        if error_is_transient(value, depth + 1):
            return True
    return False


def latest_completion_error(path: Path, max_bytes: int) -> tuple[bool, bool, bool, str]:
    for line in iter_reverse_lines(path, max_bytes):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, UnicodeError):
            continue
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        event_type = event.get("type")
        payload_type = payload.get("type") if isinstance(payload, dict) else None
        if event_type == "task_complete":
            error = event.get("error")
            return True, error_is_transient(error), bool(error), "completed"
        if event_type == "event_msg" and payload_type == "task_complete":
            error = payload.get("error")
            return True, error_is_transient(error), bool(error), "completed"
        if event_type == "turn_context" or (
            event_type == "event_msg" and payload_type in ("task_started", "turn_started")
        ):
            return False, False, False, "in_progress"
    return False, False, False, "unknown"


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    values: list[str] = []
    for item in content:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            values.append(item["text"])
    return "\n".join(values)


def event_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def claude_session_match(
    path: Path,
    marker: str,
    cwd: str,
    max_bytes: int,
) -> dict[str, Any] | None:
    consumed = 0
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                consumed += len(line.encode("utf-8", errors="replace"))
                if consumed > max_bytes:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("type") != "user":
                    continue
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                text = content_text(message.get("content"))
                if not text:
                    continue
                if marker not in text or event.get("cwd") != cwd:
                    return None
                session_id = str(event.get("sessionId") or event.get("session_id") or path.stem)
                if not SESSION_ID_RE.fullmatch(session_id):
                    return None
                return {
                    "session_id": session_id,
                    "timestamp": event_timestamp(event.get("timestamp")),
                    "state_path": path.resolve(),
                }
    except OSError:
        return None
    return None


def claude_completion_error(path: Path, max_bytes: int) -> tuple[bool, bool, bool, str]:
    in_last_turn = False
    last_unfinished_error: Any = None
    for line in iter_reverse_lines(path, max_bytes):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "user" and not in_last_turn:
            return False, False, False, "in_progress"
        if event.get("type") == "system" and event.get("subtype") == "turn_duration":
            if in_last_turn:
                break
            in_last_turn = True
            continue
        if not event.get("isApiErrorMessage"):
            continue
        text = content_text(event.get("message", {}).get("content")) if isinstance(event.get("message"), dict) else ""
        if in_last_turn:
            return True, error_is_transient(text), True, "completed"
        last_unfinished_error = text
    if last_unfinished_error is not None:
        return False, error_is_transient(last_unfinished_error), True, "in_progress"
    return in_last_turn, False, False, "completed" if in_last_turn else "unknown"


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def json_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def opencode_session_candidates(
    connection: sqlite3.Connection,
    cwd: str,
    created_at: datetime | None,
) -> list[dict[str, Any]]:
    tables = table_names(connection)
    candidates: dict[str, dict[str, Any]] = {}
    for table, version in (("session_v2", 2), ("session", 1)):
        if table not in tables:
            continue
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if not {"id", "directory", "time_created", "time_updated"}.issubset(columns):
            continue
        where = ["directory = ?"]
        params: list[Any] = [cwd]
        if created_at is not None:
            start = int((created_at - CREATED_AT_WINDOW).timestamp() * 1000)
            end = int((created_at + CREATED_AT_WINDOW).timestamp() * 1000)
            where.extend(["time_created BETWEEN ? AND ?", "time_updated >= ?"])
            params.extend([start, end, start])
        rows = connection.execute(
            f"SELECT id, directory, time_created, time_updated FROM {table} WHERE {' AND '.join(where)}",
            params,
        ).fetchall()
        for session_id, directory, created, updated in rows:
            session_id = str(session_id)
            if session_id in candidates:
                continue
            candidates[session_id] = {
                "session_id": session_id,
                "version": version,
                "created_ms": int(created),
                "updated_ms": int(updated),
                "distance_ms": abs(int(created) - int(created_at.timestamp() * 1000))
                if created_at is not None
                else 0,
            }
    return sorted(candidates.values(), key=lambda item: int(item["distance_ms"]))


def opencode_first_user_text(
    connection: sqlite3.Connection,
    session_id: str,
    version: int,
) -> str:
    tables = table_names(connection)
    if version == 2 and "session_message" in tables:
        rows = connection.execute(
            "SELECT type, data FROM session_message WHERE session_id=? ORDER BY seq, id LIMIT 50",
            (session_id,),
        ).fetchall()
        for kind, data in rows:
            value = json_value(data)
            if kind == "user" and isinstance(value.get("text"), str):
                return value["text"]
        return ""

    if "message" not in tables:
        return ""
    rows = connection.execute(
        "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created, id LIMIT 50",
        (session_id,),
    ).fetchall()
    for message_id, data in rows:
        value = json_value(data)
        if value.get("role") != "user":
            continue
        if "part" not in tables:
            return content_text(value.get("content"))
        parts = connection.execute(
            "SELECT data FROM part WHERE message_id=? ORDER BY time_created, id",
            (message_id,),
        ).fetchall()
        texts = []
        for (part_data,) in parts:
            part = json_value(part_data)
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
        return "\n".join(texts)
    return ""


def opencode_completion_error(
    connection: sqlite3.Connection,
    session_id: str,
    version: int,
) -> tuple[bool, bool, bool, str]:
    tables = table_names(connection)
    if version == 2 and "session_message" in tables:
        rows = connection.execute(
            "SELECT type, data FROM session_message WHERE session_id=? ORDER BY seq DESC, id DESC LIMIT 50",
            (session_id,),
        ).fetchall()
        completion_found = False
        failed_idle = False
        for kind, data in rows:
            value = json_value(data)
            if kind == "idle":
                completion_found = True
                outcome = str(value.get("outcome", ""))
                if outcome == "succeeded":
                    return True, False, False, "completed"
                if outcome in {"failed", "error"}:
                    failed_idle = True
                continue
            if kind == "assistant":
                if value.get("error"):
                    return True, error_is_transient(value["error"]), True, "completed"
                if not completion_found:
                    return False, False, False, "in_progress"
                continue
            if kind == "user":
                if completion_found:
                    return True, False, False, "completed"
                return False, False, False, "in_progress"
        return completion_found, False, failed_idle, "completed" if completion_found else "unknown"

    if "message" not in tables:
        return False, False, False, "unknown"
    rows = connection.execute(
        "SELECT data FROM message WHERE session_id=? ORDER BY time_created DESC, id DESC LIMIT 1",
        (session_id,),
    ).fetchall()
    for (data,) in rows:
        value = json_value(data)
        if value.get("role") == "user":
            return False, False, False, "in_progress"
        if value.get("role") != "assistant":
            return False, False, False, "unknown"
        if value.get("error"):
            return True, error_is_transient(value["error"]), True, "completed"
        return True, False, False, "completed"
    return False, False, False, "unknown"


def lookup_codex(args: argparse.Namespace, created_at: datetime | None) -> tuple[int, dict[str, Any] | None, str]:
    state_db = resolve_codex_state_db(args.state_db, args.data_dir)
    if state_db is None:
        return 3, None, "codex_state_db_missing"
    codex_home = state_db.parent.resolve()
    try:
        connection = sqlite3.connect(f"{state_db.resolve().as_uri()}?mode=ro", uri=True, timeout=2)
        connection.execute("PRAGMA query_only = ON")
        candidates = query_candidates(connection, args.run_id, args.cwd, created_at)
    except sqlite3.Error:
        return 3, None, "codex_state_db_unreadable"
    finally:
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass
    if not candidates:
        return 3, None, "codex_session_not_found"
    if len(candidates) > 1 and candidates[0]["distance_ms"] == candidates[1]["distance_ms"]:
        return 4, None, "codex_session_ambiguous"
    for candidate in candidates:
        thread_id = str(candidate.get("id") or "")
        rollout_value = str(candidate.get("rollout_path") or "")
        if not THREAD_ID_RE.fullmatch(thread_id) or not rollout_value:
            continue
        rollout = Path(rollout_value).expanduser()
        if not rollout.is_file():
            continue
        rollout = rollout.resolve()
        if not path_within(rollout, codex_home):
            continue
        completion_found, transient, failure_found, turn_state = latest_completion_error(
            rollout, args.scan_bytes
        )
        return 0, {
            "thread_id": thread_id,
            "session_id": thread_id,
            "rollout_path": rollout,
            "state_path": rollout,
            "source": "codex-rollout",
            "transient_failure": 1 if transient else 0,
            "failure_found": 1 if failure_found else 0,
            "completion_found": 1 if completion_found else 0,
            "turn_state": turn_state,
        }, "found"
    return 3, None, "codex_rollout_missing_or_outside_home"


def lookup_claude(args: argparse.Namespace, created_at: datetime | None) -> tuple[int, dict[str, Any] | None, str]:
    config_root = resolve_claude_data_dir(args.data_dir)
    projects = config_root / "projects"
    if not projects.is_dir():
        return 3, None, "claude_projects_missing"
    marker = f"run_id={args.run_id}"
    candidates: list[dict[str, Any]] = []
    start_ms = int(created_at.timestamp() * 1000) if created_at is not None else 0
    project_key = re.sub(r"[^A-Za-z0-9]", "-", args.cwd)
    exact_project = projects / project_key
    paths = list(exact_project.glob("*.jsonl")) if exact_project.is_dir() else []
    if not paths:
        paths = list(projects.glob("*/*.jsonl"))
    for path in paths:
        try:
            if created_at is not None and int(path.stat().st_mtime * 1000) < start_ms - int(CREATED_AT_WINDOW.total_seconds() * 1000):
                continue
        except OSError:
            continue
        match = claude_session_match(path, marker, args.cwd, args.scan_bytes)
        if match is None:
            continue
        timestamp = match.pop("timestamp", None)
        distance = abs(int(timestamp.timestamp() * 1000) - start_ms) if timestamp and created_at else 0
        match["distance_ms"] = distance
        match["transient_failure"], match["failure_found"], match["completion_found"] = (0, 0, 0)
        completion_found, transient, failure_found, turn_state = claude_completion_error(
            match["state_path"], args.scan_bytes
        )
        match["transient_failure"] = 1 if transient else 0
        match["failure_found"] = 1 if failure_found else 0
        match["completion_found"] = 1 if completion_found else 0
        match["turn_state"] = turn_state
        match["source"] = "claude-session-jsonl"
        candidates.append(match)
    if not candidates:
        return 3, None, "claude_session_not_found"
    candidates.sort(key=lambda item: int(item["distance_ms"]))
    if len(candidates) > 1 and candidates[0]["distance_ms"] == candidates[1]["distance_ms"]:
        return 4, None, "claude_session_ambiguous"
    return 0, candidates[0], "found"


def lookup_opencode(args: argparse.Namespace, created_at: datetime | None) -> tuple[int, dict[str, Any] | None, str]:
    state_db = resolve_opencode_state_db(args.state_db, args.data_dir)
    if state_db is None:
        return 3, None, "opencode_state_db_missing"
    try:
        connection = sqlite3.connect(f"{state_db.resolve().as_uri()}?mode=ro", uri=True, timeout=2)
        connection.execute("PRAGMA query_only = ON")
        candidates = opencode_session_candidates(connection, args.cwd, created_at)
        marker = f"run_id={args.run_id}"
        matches = [
            candidate
            for candidate in candidates
            if marker in opencode_first_user_text(connection, candidate["session_id"], candidate["version"])
        ]
        if not matches:
            return 3, None, "opencode_session_not_found"
        if len(matches) > 1 and matches[0]["distance_ms"] == matches[1]["distance_ms"]:
            return 4, None, "opencode_session_ambiguous"
        selected = matches[0]
        completion_found, transient, failure_found, turn_state = opencode_completion_error(
            connection, selected["session_id"], selected["version"]
        )
    except sqlite3.Error:
        return 3, None, "opencode_state_db_unreadable"
    finally:
        try:
            connection.close()
        except (UnboundLocalError, sqlite3.Error):
            pass
    return 0, {
        "session_id": selected["session_id"],
        "state_path": state_db.resolve(),
        "source": f"opencode-v{selected['version']}-sqlite",
        "transient_failure": 1 if transient else 0,
        "failure_found": 1 if failure_found else 0,
        "completion_found": 1 if completion_found else 0,
        "turn_state": turn_state,
    }, "found"


def clean_output_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ")


def emit(record: dict[str, Any]) -> None:
    for key in (
        "session_id",
        "thread_id",
        "state_path",
        "rollout_path",
        "source",
        "transient_failure",
        "failure_found",
        "completion_found",
        "turn_state",
    ):
        print(f"{key}={clean_output_value(record.get(key))}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not RUN_ID_RE.fullmatch(args.run_id):
        print("status=invalid reason=invalid_run_id", file=sys.stderr)
        return 2
    if not os.path.isabs(args.cwd):
        print("status=invalid reason=cwd_not_absolute", file=sys.stderr)
        return 2
    if args.scan_bytes <= 0:
        print("status=invalid reason=scan_bytes_not_positive", file=sys.stderr)
        return 2
    created_at = parse_created_at(args.created_at)
    if args.created_at and created_at is None:
        print("status=invalid reason=invalid_created_at", file=sys.stderr)
        return 2

    lookup = {
        "codex": lookup_codex,
        "claude": lookup_claude,
        "opencode": lookup_opencode,
    }[args.agent]
    code, report, reason = lookup(args, created_at)
    if report is None:
        print(f"status=unavailable reason={reason}", file=sys.stderr)
        return code
    emit(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
