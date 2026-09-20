#!/usr/bin/env python3
"""Minimal Responses-to-Chat Completions bridge for agent launchers."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def json_text(value):
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(value)


def content_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json_text(content)
    parts = []
    for part in content:
        if not isinstance(part, dict):
            parts.append(str(part))
            continue
        part_type = str(part.get("type") or "")
        if part_type in {"input_text", "output_text", "text"}:
            parts.append(str(part.get("text") or ""))
        elif part_type in {"input_image", "image_url"}:
            parts.append("[image]")
    return "\n".join(value for value in parts if value)


def normalize_tool_choice(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return "auto"
    if value.get("type") == "function" and value.get("name"):
        return {"type": "function", "function": {"name": str(value["name"])}}
    return "auto"


def responses_to_chat(payload):
    messages = []
    instructions = str(payload.get("instructions") or "").strip()
    if instructions:
        messages.append({"role": "system", "content": instructions})

    for item in payload.get("input") or []:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "message")
        if item_type == "message":
            role = str(item.get("role") or "user")
            if role == "developer":
                role = "system"
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            messages.append({"role": role, "content": content_text(item.get("content"))})
        elif item_type == "function_call":
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": str(item.get("call_id") or item.get("id") or "call_" + uuid.uuid4().hex),
                            "type": "function",
                            "function": {
                                "name": str(item.get("name") or ""),
                                "arguments": json_text(item.get("arguments")),
                            },
                        }
                    ],
                }
            )
        elif item_type == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(item.get("call_id") or ""),
                    "content": json_text(item.get("output")),
                }
            )

    tools = []
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )

    body = {
        "model": str(payload.get("model") or ""),
        "messages": messages,
        "stream": False,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = normalize_tool_choice(payload.get("tool_choice"))
        body["parallel_tool_calls"] = bool(payload.get("parallel_tool_calls", True))
    max_tokens = payload.get("max_output_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        body["max_tokens"] = max_tokens
    elif len(messages) > 0:
        body["max_tokens"] = 65536
    reasoning = payload.get("reasoning") or {}
    if isinstance(reasoning, dict) and reasoning.get("effort"):
        body["reasoning_effort"] = str(reasoning["effort"])
    return body


def anthropic_system_text(system):
    if isinstance(system, str):
        return system
    return content_text(system)


def anthropic_tool_choice(value):
    if not isinstance(value, dict):
        return "auto"
    choice_type = str(value.get("type") or "")
    if choice_type == "any":
        return "required"
    if choice_type == "none":
        return "none"
    if choice_type == "tool" and value.get("name"):
        return {"type": "function", "function": {"name": str(value["name"])}}
    return "auto"


def messages_to_chat(payload):
    messages = []
    system = anthropic_system_text(payload.get("system")).strip()
    if system:
        messages.append({"role": "system", "content": system})

    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = message.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            messages.append({"role": role, "content": content_text(content)})
            continue
        text_parts = []
        tool_calls = []

        def flush_text():
            nonlocal text_parts
            if text_parts:
                messages.append({"role": role, "content": "\n".join(text_parts)})
                text_parts = []

        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            block_type = str(block.get("type") or "")
            if block_type == "text":
                text_parts.append(str(block.get("text") or ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or "call_" + uuid.uuid4().hex),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or ""),
                            "arguments": json_text(block.get("input")),
                        },
                    }
                )
            elif block_type == "tool_result":
                flush_text()
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id") or ""),
                        "content": content_text(block.get("content")),
                    }
                )
            elif block_type == "image":
                text_parts.append("[image]")
        if role == "assistant" and tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                    "tool_calls": tool_calls,
                }
            )
        else:
            flush_text()

    tools = []
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )

    body = {
        "model": str(payload.get("model") or ""),
        "messages": messages,
        "stream": False,
    }
    if payload.get("max_tokens"):
        body["max_tokens"] = int(payload["max_tokens"])
    if tools:
        body["tools"] = tools
        body["tool_choice"] = anthropic_tool_choice(payload.get("tool_choice"))
    for name in ("temperature", "top_p"):
        if payload.get(name) is not None:
            body[name] = payload[name]
    if payload.get("stop_sequences"):
        body["stop"] = payload["stop_sequences"]
    return body


def response_base(payload, response_id):
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "in_progress",
        "model": str(payload.get("model") or ""),
        "output": [],
        "error": None,
        "incomplete_details": None,
        "instructions": payload.get("instructions"),
        "max_output_tokens": payload.get("max_output_tokens"),
        "parallel_tool_calls": bool(payload.get("parallel_tool_calls", True)),
        "previous_response_id": payload.get("previous_response_id"),
        "reasoning": payload.get("reasoning"),
        "store": False,
        "temperature": payload.get("temperature"),
        "text": payload.get("text") or {"format": {"type": "text"}},
        "tool_choice": payload.get("tool_choice", "auto"),
        "tools": payload.get("tools") or [],
        "top_p": payload.get("top_p"),
        "truncation": payload.get("truncation", "disabled"),
        "usage": None,
    }


def usage_from_chat(value):
    value = value if isinstance(value, dict) else {}
    prompt_details = value.get("prompt_tokens_details") or {}
    completion_details = value.get("completion_tokens_details") or {}
    return {
        "input_tokens": int(value.get("prompt_tokens") or 0),
        "input_tokens_details": {
            "cached_tokens": int(prompt_details.get("cached_tokens") or 0),
        },
        "output_tokens": int(value.get("completion_tokens") or 0),
        "output_tokens_details": {
            "reasoning_tokens": int(completion_details.get("reasoning_tokens") or 0),
        },
        "total_tokens": int(value.get("total_tokens") or 0),
    }


def chat_to_response_events(payload, chat):
    response_id = "resp_" + uuid.uuid4().hex
    base = response_base(payload, response_id)
    events = []
    next_sequence = 0

    def add(name, body):
        nonlocal next_sequence
        body = dict(body)
        body["type"] = name
        body["sequence_number"] = next_sequence
        next_sequence += 1
        events.append((name, body))

    add("response.created", {"response": base})
    add("response.in_progress", {"response": base})

    output_items = []
    choices = chat.get("choices") if isinstance(chat, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    if not isinstance(message, dict):
        message = {}
    text = message.get("content")
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = content_text(text)

    if text:
        item_id = "msg_" + uuid.uuid4().hex
        output_index = len(output_items)
        in_progress = {
            "id": item_id,
            "type": "message",
            "status": "in_progress",
            "role": "assistant",
            "content": [],
        }
        completed = {
            "id": item_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": text,
                    "annotations": [],
                    "logprobs": [],
                }
            ],
        }
        add("response.output_item.added", {"output_index": output_index, "item": in_progress})
        add(
            "response.content_part.added",
            {
                "item_id": item_id,
                "output_index": output_index,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": [], "logprobs": []},
            },
        )
        add(
            "response.output_text.delta",
            {
                "item_id": item_id,
                "output_index": output_index,
                "content_index": 0,
                "delta": text,
                "logprobs": [],
            },
        )
        add(
            "response.output_text.done",
            {
                "item_id": item_id,
                "output_index": output_index,
                "content_index": 0,
                "text": text,
                "logprobs": [],
            },
        )
        add(
            "response.content_part.done",
            {
                "item_id": item_id,
                "output_index": output_index,
                "content_index": 0,
                "part": {"type": "output_text", "text": text, "annotations": [], "logprobs": []},
            },
        )
        add("response.output_item.done", {"output_index": output_index, "item": completed})
        output_items.append(completed)

    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        tool_calls = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") or {}
        if not isinstance(function, dict):
            function = {}
        item_id = "fc_" + uuid.uuid4().hex
        call_id = str(tool_call.get("id") or "call_" + uuid.uuid4().hex)
        name = str(function.get("name") or "")
        arguments = json_text(function.get("arguments"))
        output_index = len(output_items)
        in_progress = {
            "id": item_id,
            "type": "function_call",
            "status": "in_progress",
            "arguments": "",
            "call_id": call_id,
            "name": name,
        }
        completed = dict(in_progress)
        completed["status"] = "completed"
        completed["arguments"] = arguments
        add("response.output_item.added", {"output_index": output_index, "item": in_progress})
        add(
            "response.function_call_arguments.delta",
            {
                "item_id": item_id,
                "output_index": output_index,
                "delta": arguments,
            },
        )
        add(
            "response.function_call_arguments.done",
            {
                "item_id": item_id,
                "output_index": output_index,
                "arguments": arguments,
            },
        )
        add("response.output_item.done", {"output_index": output_index, "item": completed})
        output_items.append(completed)

    done = dict(base)
    done.update(
        {
            "status": "completed",
            "output": output_items,
            "usage": usage_from_chat(chat.get("usage") if isinstance(chat, dict) else {}),
        }
    )
    add("response.completed", {"response": done})
    return events


def chat_to_anthropic_events(payload, chat):
    choices = chat.get("choices") if isinstance(chat, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    if not isinstance(message, dict):
        message = {}
    text = message.get("content")
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = content_text(text)
    if not text and message.get("reasoning_content"):
        text = str(message.get("reasoning_content"))
    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        tool_calls = []
    usage = chat.get("usage") if isinstance(chat, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    message_id = "msg_" + uuid.uuid4().hex
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": str(payload.get("model") or ""),
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": input_tokens, "output_tokens": 0},
                },
            },
        )
    ]
    block_index = 0
    if text:
        events.extend(
            [
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {"type": "text", "text": ""},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {"type": "text_delta", "text": text},
                    },
                ),
                ("content_block_stop", {"type": "content_block_stop", "index": block_index}),
            ]
        )
        block_index += 1
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") or {}
        if not isinstance(function, dict):
            function = {}
        tool_id = str(tool_call.get("id") or "toolu_" + uuid.uuid4().hex)
        events.extend(
            [
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": str(function.get("name") or ""),
                            "input": {},
                        },
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": json_text(function.get("arguments")),
                        },
                    },
                ),
                ("content_block_stop", {"type": "content_block_stop", "index": block_index}),
            ]
        )
        block_index += 1
    finish_reason = str(choice.get("finish_reason") or "stop")
    stop_reason = {
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "stop": "end_turn",
    }.get(finish_reason, "end_turn")
    events.extend(
        [
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                    "usage": {"output_tokens": output_tokens},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )
    return events


class UpstreamError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def fetch_chat(args, payload, incoming_headers, converter):
    url = args.upstream_base.rstrip("/") + "/chat/completions"
    body = json.dumps(converter(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "configure-agent-bridge/1.0",
    }
    for name in (
        "session-id",
        "thread-id",
        "x-codex-beta-features",
        "x-codex-window-id",
        "x-codex-turn-metadata",
        "x-client-request-id",
        "originator",
    ):
        value = incoming_headers.get(name)
        if value:
            headers[name] = value
    api_key = os.environ.get(args.api_key_env, "")
    if api_key:
        if args.auth_mode == "api_key":
            headers["x-api-key"] = api_key
        else:
            headers["Authorization"] = "Bearer " + api_key
    session_id = (
        incoming_headers.get("session-id")
        or incoming_headers.get("x-opencode-session")
        or args.session_id
    )
    if session_id:
        headers["x-opencode-session"] = session_id
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        message = raw.decode("utf-8", "replace") or str(exc)
        raise UpstreamError(exc.code, message)
    except Exception as exc:
        raise UpstreamError(502, str(exc))
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise UpstreamError(502, "upstream returned invalid JSON: %s" % exc)


def write_ready_file(path, port):
    if not path:
        return
    temporary = path + ".tmp.%d" % os.getpid()
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(str(port) + "\n")
    os.replace(temporary, path)


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "configure-agent-bridge/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), file=sys.stderr, flush=True)

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") == "/healthz":
            self.send_json(200, {"ok": True})
            return
        self.send_json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path.rstrip("/")
        if path not in {"/v1/responses", "/v1/messages"}:
            self.send_json(404, {"error": {"message": "unsupported path: %s" % self.path}})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/v1/messages":
                chat = fetch_chat(self.server.bridge_args, payload, self.headers, messages_to_chat)
                events = chat_to_anthropic_events(payload, chat)
            else:
                chat = fetch_chat(self.server.bridge_args, payload, self.headers, responses_to_chat)
                events = chat_to_response_events(payload, chat)
        except UpstreamError as exc:
            if path == "/v1/messages":
                self.send_json(
                    exc.status,
                    {"type": "error", "error": {"type": "api_error", "message": exc.message}},
                )
            else:
                self.send_json(exc.status, {"error": {"message": exc.message, "type": "upstream_error"}})
            return
        except Exception as exc:
            self.send_json(500, {"error": {"message": str(exc), "type": "bridge_error"}})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for name, event in events:
            data = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.wfile.write(b"event: " + name.encode("ascii") + b"\n")
            self.wfile.write(b"data: " + data + b"\n\n")
            self.wfile.flush()


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--upstream-base", required=True)
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--auth-mode", choices=("bearer", "api_key"), default="bearer")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--ready-file", default="")
    parser.add_argument("--timeout", type=int, default=300)
    return parser


def main():
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.listen_host, args.port), BridgeHandler)
    server.daemon_threads = True
    server.bridge_args = args
    write_ready_file(args.ready_file, server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
