#!/usr/bin/env python3
"""Queue and start a recovery turn on a running Codex app-server thread."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import time
import uuid
from pathlib import Path
from typing import Any


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_TIMEOUT = 10.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True, help="Unix app-server URL: unix:///path/to.sock")
    parser.add_argument("--thread", required=True, help="Codex thread id")
    parser.add_argument("--message", required=True, help="Message to queue and start")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser.parse_args(argv)


def unix_socket_path(remote: str) -> Path:
    prefix = "unix://"
    if not remote.startswith(prefix):
        raise ValueError("remote_must_be_unix")
    value = remote[len(prefix) :]
    if not value.startswith("/"):
        raise ValueError("unix_socket_must_be_absolute")
    path = Path(value)
    if not path.is_socket():
        raise ValueError("unix_socket_missing")
    return path


def recv_exact(stream: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise ConnectionError("app_server_closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_http_headers(stream: socket.socket) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = stream.recv(4096)
        if not chunk:
            raise ConnectionError("app_server_closed_during_handshake")
        data.extend(chunk)
        if len(data) > 64 * 1024:
            raise ValueError("app_server_handshake_too_large")
    return bytes(data)


def connect_websocket(path: Path, timeout: float) -> socket.socket:
    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stream.settimeout(timeout)
    stream.connect(str(path))
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET /rpc HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Connection: Upgrade\r\n"
        "Upgrade: websocket\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "\r\n"
    )
    stream.sendall(request.encode("ascii"))
    response = recv_http_headers(stream)
    header_text = response.decode("latin-1", errors="replace")
    if not header_text.startswith("HTTP/1.1 101"):
        stream.close()
        raise ValueError("app_server_websocket_upgrade_failed")
    expected = base64.b64encode(
        hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()
    ).decode("ascii")
    headers = {}
    for line in header_text.split("\r\n")[1:]:
        name, separator, value = line.partition(":")
        if separator:
            headers[name.strip().lower()] = value.strip()
    if headers.get("sec-websocket-accept") != expected:
        stream.close()
        raise ValueError("app_server_websocket_accept_mismatch")
    return stream


def send_frame(stream: socket.socket, opcode: int, payload: bytes) -> None:
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes((first, 0x80 | length))
    elif length <= 0xFFFF:
        header = bytes((first, 0x80 | 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 0x80 | 127)) + struct.pack("!Q", length)
    mask = os.urandom(4)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    stream.sendall(header + mask + masked)


def recv_frame(stream: socket.socket) -> tuple[int, bool, bytes]:
    first, second = recv_exact(stream, 2)
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", recv_exact(stream, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(stream, 8))[0]
    mask = recv_exact(stream, 4) if masked else b""
    payload = recv_exact(stream, length)
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return opcode, fin, payload


def recv_message(stream: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        opcode, fin, payload = recv_frame(stream)
        if opcode == 0x8:
            raise ConnectionError("app_server_closed")
        if opcode == 0x9:
            send_frame(stream, 0xA, payload)
            continue
        if opcode in (0x1, 0x2):
            chunks = [payload]
        elif opcode == 0x0 and chunks:
            chunks.append(payload)
        else:
            continue
        if fin:
            return b"".join(chunks).decode("utf-8")


def send_json(stream: socket.socket, payload: dict[str, Any]) -> None:
    send_frame(stream, 0x1, json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def request(
    stream: socket.socket,
    request_id: int,
    method: str,
    params: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    send_json(stream, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(method)
        stream.settimeout(remaining)
        event = json.loads(recv_message(stream))
        if event.get("id") != request_id:
            continue
        if "error" in event:
            error = event.get("error")
            code = error.get("code") if isinstance(error, dict) else "unknown"
            message = error.get("message") if isinstance(error, dict) else "unknown"
            raise RuntimeError(f"{method}_failed code={code} message={message}")
        result = event.get("result")
        if not isinstance(result, dict):
            raise ValueError(f"{method}_invalid_result")
        return result


def resume_thread(args: argparse.Namespace) -> dict[str, str]:
    stream = connect_websocket(unix_socket_path(args.remote), args.timeout)
    try:
        request(
            stream,
            1,
            "initialize",
            {
                "clientInfo": {"name": "configure-agent-codex-resume", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
            args.timeout,
        )
        send_json(stream, {"jsonrpc": "2.0", "method": "initialized"})
        request(stream, 2, "thread/resume", {"threadId": args.thread, "excludeTurns": True}, args.timeout)
        added = request(
            stream,
            3,
            "thread/queue/add",
            {
                "threadId": args.thread,
                "clientUserMessageId": str(uuid.uuid4()),
                "input": [{"type": "text", "text": args.message}],
            },
            args.timeout,
        )
        queued = added.get("queuedSubmission")
        queued_id = queued.get("id") if isinstance(queued, dict) else None
        if not isinstance(queued_id, str) or not queued_id:
            raise ValueError("thread_queue_add_missing_id")
        started = request(
            stream,
            4,
            "thread/queue/start",
            {"threadId": args.thread, "queuedSubmissionId": queued_id},
            args.timeout,
        )
        turn = started.get("turn")
        turn_id = turn.get("id") if isinstance(turn, dict) else None
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("thread_queue_start_missing_turn")
        return {"thread_id": args.thread, "queued_id": queued_id, "turn_id": turn_id}
    finally:
        try:
            send_frame(stream, 0x8, b"")
        except OSError:
            pass
        stream.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        print("status=invalid reason=invalid_timeout", file=sys.stderr)
        return 2
    try:
        result = resume_thread(args)
    except (ConnectionError, OSError, TimeoutError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        reason = str(error).replace("\n", " ")
        print(f"status=failed reason={reason}", file=sys.stderr)
        return 1
    print(
        "status=resumed "
        f"thread_id={result['thread_id']} queued_id={result['queued_id']} turn_id={result['turn_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
