#!/usr/bin/env python3
"""Statically audit Codex plugin and hook manifests without executing them.

The schema and risk checks are adapted from the hook/plugin manifests and
validation practices in ECC and oh-my-codex, both pinned under refer/git-rep.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


MAX_JSON_BYTES = 1024 * 1024
MAX_DISCOVERED_MANIFESTS = 200
MAX_SCANNED_DIRECTORIES = 5000
ALLOWED_HOOK_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "SubagentStart",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "InstructionsLoaded",
    "TeammateIdle",
    "TaskCompleted",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "SessionEnd",
}
SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?P<name>(?<![A-Za-z0-9])[A-Za-z0-9_]*?"
    r"(?:api[_-]?key|access[_-]?token|authorization|cookie|password|secret|token)"
    r"[A-Za-z0-9_]*)(?P<separator>\s*[:=]\s*)"
    r"(?P<value>[^\n'\"`;|&,}]+)",
    re.IGNORECASE,
)
SENSITIVE_KEY_RE = re.compile(
    r"api[_-]?key|access[_-]?token|authorization|cookie|password|secret|(?:^|[_-])token(?:$|[_-])",
    re.IGNORECASE,
)
ENV_REFERENCE_RE = re.compile(
    r"^(?:\$\{?[A-Za-z_][A-Za-z0-9_]*(?::?-[^}]*)?\}?|"
    r"%[A-Za-z_][A-Za-z0-9_]*%|env:[A-Za-z_][A-Za-z0-9_]*|<[^>]+>)$",
    re.IGNORECASE,
)
RUNTIME_INSTALL_COMMANDS = {
    "bunx",
    "docker",
    "npx",
    "npm",
    "pip",
    "pip3",
    "pnpm",
    "uv",
    "uvx",
    "yarn",
}


class DiscoveryError(RuntimeError):
    """Raised when bounded manifest discovery cannot produce a complete result."""


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str
    location: str = ""


@dataclass
class AuditResult:
    manifest: str
    plugin_name: Optional[str] = None
    plugin_version: Optional[str] = None
    hook_manifests: List[str] = None
    findings: List[Finding] = None

    def __post_init__(self) -> None:
        if self.hook_manifests is None:
            self.hook_manifests = []
        if self.findings is None:
            self.findings = []


def _redact_sensitive_assignments(text: str) -> str:
    return SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('name')}{match.group('separator')}[REDACTED]",
        text,
    )


def _display_text(value: object, limit: int = 240) -> str:
    escaped = []
    for character in str(value):
        codepoint = ord(character)
        if character == "\n":
            escaped.append(r"\n")
        elif character == "\r":
            escaped.append(r"\r")
        elif character == "\t":
            escaped.append(r"\t")
        elif codepoint < 32 or codepoint == 127:
            escaped.append(f"\\x{codepoint:02x}")
        else:
            escaped.append(character)
    text = _redact_sensitive_assignments("".join(escaped))
    if len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


def _is_literal_secret(value: str) -> bool:
    candidate = value.strip().strip("'\"").strip()
    if len(candidate) < 8:
        return False
    if ENV_REFERENCE_RE.fullmatch(candidate):
        return False
    if re.fullmatch(r"(?:bearer\s+)?[$%]\{?[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}?", candidate, re.I):
        return False
    return True


def _strict_json_object(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _finding(
    findings: List[Finding],
    severity: str,
    code: str,
    path: Path,
    message: str,
    location: str = "",
) -> None:
    findings.append(
        Finding(
            severity,
            code,
            _display_text(path.as_posix(), 500),
            message,
            _display_text(location),
        )
    )


def _load_json(path: Path, max_bytes: int = MAX_JSON_BYTES) -> Tuple[Optional[object], Optional[str]]:
    try:
        if path.stat().st_size > max_bytes:
            return None, f"文件超过静态审计大小上限 {max_bytes} bytes"
        return (
            json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_json_constant,
            ),
            None,
        )
    except OSError as error:
        return None, f"无法读取文件：{error.__class__.__name__}"
    except ValueError:
        return None, "JSON 无法解析，或包含重复键/非有限数值"
    except UnicodeError:
        return None, "JSON 不是有效 UTF-8"
    except RecursionError:
        return None, "JSON 嵌套层级过深"


def _resolve_manifest_reference(
    plugin_root: Path,
    value: object,
    field: str,
    findings: List[Finding],
    manifest_path: Path,
    must_be_file: bool = False,
    allowed_boundary: Optional[Path] = None,
) -> Optional[Path]:
    if not isinstance(value, str) or not value.strip():
        _finding(findings, "high", "PLUGIN_PATH_INVALID", manifest_path, f"{field} 必须是非空相对路径")
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        _finding(findings, "critical", "PLUGIN_PATH_ABSOLUTE", manifest_path, f"{field} 不允许绝对路径")
        return None
    try:
        root = plugin_root.resolve(strict=True)
        lexical = (root / candidate).resolve(strict=False)
    except (OSError, RuntimeError):
        _finding(findings, "high", "PLUGIN_PATH_MISSING", manifest_path, f"{field} 指向不存在的路径")
        return None
    inside_plugin = True
    try:
        lexical.relative_to(root)
    except ValueError:
        inside_plugin = False
    if not inside_plugin:
        boundary = allowed_boundary.resolve() if allowed_boundary is not None else None
        inside_boundary = False
        if boundary is not None:
            try:
                lexical.relative_to(boundary)
                inside_boundary = True
            except ValueError:
                pass
        if not inside_boundary:
            _finding(findings, "critical", "PLUGIN_PATH_ESCAPE", manifest_path, f"{field} 越出插件根目录")
            return None
        _finding(
            findings,
            "medium",
            "PLUGIN_PATH_OUTSIDE_ROOT",
            manifest_path,
            f"{field} 引用插件父目录，但仍位于审计根内",
        )
    try:
        resolved = lexical.resolve(strict=True)
    except (OSError, RuntimeError):
        _finding(findings, "high", "PLUGIN_PATH_MISSING", manifest_path, f"{field} 指向不存在的路径")
        return None
    if allowed_boundary is not None:
        try:
            resolved.relative_to(allowed_boundary.resolve())
        except ValueError:
            _finding(findings, "critical", "PLUGIN_PATH_ESCAPE", manifest_path, f"{field} 解析后越出审计根目录")
            return None
    if must_be_file and not resolved.is_file():
        _finding(findings, "high", "PLUGIN_PATH_NOT_FILE", manifest_path, f"{field} 必须是普通文件")
        return None
    return resolved


def _audit_reference_values(
    plugin_root: Path,
    value: object,
    field: str,
    findings: List[Finding],
    manifest_path: Path,
    allowed_boundary: Optional[Path] = None,
) -> None:
    values = value if isinstance(value, list) else [value]
    if not values:
        return
    for index, item in enumerate(values):
        label = f"{field}[{index}]" if isinstance(value, list) else field
        _resolve_manifest_reference(
            plugin_root,
            item,
            label,
            findings,
            manifest_path,
            allowed_boundary=allowed_boundary,
        )


def _audit_command_text(
    text: str,
    path: Path,
    findings: List[Finding],
    location: str,
    plugin_root: Optional[Path] = None,
    allowed_boundary: Optional[Path] = None,
) -> None:
    lowered = text.lower()
    critical_patterns = (
        (r"\brm\s+-[^\s]*r[^\s]*\b", "HOOK_DESTRUCTIVE_RM", "命令包含递归删除"),
        (r"\bsudo\b", "HOOK_PRIVILEGE_ESCALATION", "命令要求提权"),
        (r"git\s+reset\s+--hard", "HOOK_GIT_RESET_HARD", "命令包含 git reset --hard"),
        (r"git\s+clean\s+-[^\n]*f", "HOOK_GIT_CLEAN_FORCE", "命令包含强制 git clean"),
        (r"\bdd\s+if=", "HOOK_DD", "命令包含原始磁盘写入"),
        (r"\bmkfs(?:\.|\s)", "HOOK_MKFS", "命令包含文件系统格式化"),
        (r"(?:curl|wget)[^\n|]*\|\s*(?:sh|bash|zsh)", "HOOK_REMOTE_PIPE", "命令把网络内容直接管道给 shell"),
    )
    for pattern, code, message in critical_patterns:
        if re.search(pattern, lowered):
            _finding(findings, "critical", code, path, message, location)

    medium_patterns = (
        (r"\b(?:bash|sh|zsh)\s+-c\b", "HOOK_SHELL_EVAL", "命令使用 shell -c 动态执行"),
        (r"\bnode\s+(?:-e|--eval)\b", "HOOK_NODE_EVAL", "命令使用 node 动态执行"),
        (r"\bpython(?:3)?\s+-c\b", "HOOK_PYTHON_EVAL", "命令使用 Python 动态执行"),
        (r"\b(?:eval|exec)\s*\(", "HOOK_DYNAMIC_EVAL", "命令包含动态求值"),
        (r"\b(?:curl|wget)\b", "HOOK_NETWORK", "命令会访问网络"),
        (r"https?://", "HOOK_REMOTE_URL", "命令包含远程 URL"),
        (r"base64\s+(?:-d|--decode)", "HOOK_BASE64_DECODE", "命令包含 base64 解码"),
    )
    for pattern, code, message in medium_patterns:
        if re.search(pattern, lowered):
            _finding(findings, "medium", code, path, message, location)

    secret_found = "begin private key" in lowered
    for match in SENSITIVE_ASSIGNMENT_RE.finditer(text):
        if _is_literal_secret(match.group("value")):
            secret_found = True
            break
    if secret_found:
        _finding(findings, "high", "HOOK_SECRET_LITERAL", path, "命令可能包含硬编码凭据", location)

    if plugin_root is None:
        return
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = text.split()
    try:
        resolved_plugin_root = plugin_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return
    seen_paths = set()
    for token in tokens:
        if not token or token.startswith("-") or "://" in token or "$" in token or "`" in token:
            continue
        normalized = token.replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", normalized):
            key = ("HOOK_ABSOLUTE_PATH", normalized)
            if key not in seen_paths:
                seen_paths.add(key)
                _finding(findings, "medium", key[0], path, "命令包含绝对路径", location)
            continue
        if normalized.startswith("/"):
            key = ("HOOK_ABSOLUTE_PATH", normalized)
            if key not in seen_paths:
                seen_paths.add(key)
                _finding(findings, "medium", key[0], path, "命令包含绝对路径", location)
            continue
        parts = normalized.split("/")
        if ".." in parts:
            key = ("HOOK_PATH_TRAVERSAL", normalized)
            if key not in seen_paths:
                seen_paths.add(key)
                _finding(findings, "medium", key[0], path, "命令参数使用父目录路径穿越", location)
            continue
        if "/" not in normalized:
            continue
        candidate = resolved_plugin_root / normalized
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        try:
            resolved.relative_to(resolved_plugin_root)
            continue
        except ValueError:
            pass
        if allowed_boundary is not None:
            try:
                resolved.relative_to(allowed_boundary.resolve())
                key = ("HOOK_PATH_OUTSIDE_ROOT", normalized)
                if key not in seen_paths:
                    seen_paths.add(key)
                    _finding(findings, "medium", key[0], path, "命令路径解析到插件根目录外，但仍位于审计根内", location)
                continue
            except ValueError:
                pass
        key = ("HOOK_PATH_ESCAPE", normalized)
        if key not in seen_paths:
            seen_paths.add(key)
            _finding(findings, "critical", key[0], path, "命令路径解析后越出插件与审计根目录", location)


def _audit_hook_items(
    items: object,
    manifest_path: Path,
    findings: List[Finding],
    event: str,
    matcher: str,
    plugin_root: Path,
    allowed_boundary: Optional[Path],
) -> None:
    if not isinstance(items, list) or not items:
        _finding(findings, "high", "HOOK_ITEMS_INVALID", manifest_path, "hook 条目必须是非空数组", event)
        return
    for index, item in enumerate(items):
        location = f"{event}[{matcher}].hooks[{index}]"
        if not isinstance(item, dict):
            _finding(findings, "high", "HOOK_ITEM_INVALID", manifest_path, "hook 条目必须是对象", location)
            continue
        hook_type = item.get("type")
        if "async" in item and not isinstance(item.get("async"), bool):
            _finding(findings, "high", "HOOK_ASYNC_INVALID", manifest_path, "async 必须是布尔值", location)
        timeout_value = item.get("timeout")
        timeout = None
        if timeout_value is not None:
            if isinstance(timeout_value, (int, float)) and not isinstance(timeout_value, bool):
                timeout = float(timeout_value)
            else:
                _finding(findings, "high", "HOOK_TIMEOUT_INVALID", manifest_path, "timeout 必须是数字", location)
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0 or timeout > 3600):
            _finding(findings, "medium", "HOOK_TIMEOUT_RANGE", manifest_path, "hook timeout 超出 1..3600 秒范围", location)
        if hook_type == "command":
            command = item.get("command")
            if isinstance(command, str) and command.strip():
                _audit_command_text(
                    command,
                    manifest_path,
                    findings,
                    location,
                    plugin_root=plugin_root,
                    allowed_boundary=allowed_boundary,
                )
            elif isinstance(command, list) and command and all(isinstance(x, str) and x for x in command):
                _audit_command_text(
                    " ".join(command),
                    manifest_path,
                    findings,
                    location,
                    plugin_root=plugin_root,
                    allowed_boundary=allowed_boundary,
                )
            else:
                _finding(findings, "critical", "HOOK_COMMAND_INVALID", manifest_path, "command hook 缺少命令", location)
            if timeout is None:
                _finding(findings, "medium", "HOOK_TIMEOUT_MISSING", manifest_path, "command hook 未声明 timeout", location)
        elif hook_type == "http":
            _finding(findings, "high", "HOOK_HTTP_REMOTE", manifest_path, "HTTP hook 会把事件数据发送到远程端点", location)
            if not isinstance(item.get("url"), str) or not item.get("url", "").strip():
                _finding(findings, "critical", "HOOK_HTTP_URL_INVALID", manifest_path, "HTTP hook 缺少 url", location)
            if timeout is None:
                _finding(findings, "medium", "HOOK_TIMEOUT_MISSING", manifest_path, "HTTP hook 未声明 timeout", location)
        elif hook_type in ("prompt", "agent"):
            _finding(findings, "medium", "HOOK_MODEL_EXECUTION", manifest_path, "prompt/agent hook 会触发额外模型执行", location)
            if timeout is None:
                _finding(findings, "medium", "HOOK_TIMEOUT_MISSING", manifest_path, "prompt/agent hook 未声明 timeout", location)
        else:
            _finding(findings, "high", "HOOK_TYPE_INVALID", manifest_path, "未知 hook type", location)


def _audit_hooks_data(
    data: object,
    manifest_path: Path,
    findings: List[Finding],
    plugin_root: Path,
    allowed_boundary: Optional[Path],
) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        _finding(findings, "critical", "HOOKS_SCHEMA_INVALID", manifest_path, "hook manifest 缺少对象类型 hooks")
        return
    seen_ids: Dict[str, str] = {}
    for event, entries in data["hooks"].items():
        if event not in ALLOWED_HOOK_EVENTS:
            _finding(findings, "medium", "HOOK_EVENT_UNKNOWN", manifest_path, "未知 hook event", str(event))
        if not isinstance(entries, list):
            _finding(findings, "high", "HOOK_EVENT_INVALID", manifest_path, "event 配置必须是数组", str(event))
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                _finding(findings, "high", "HOOK_ENTRY_INVALID", manifest_path, "matcher 条目必须是对象", f"{event}[{index}]")
                continue
            entry_id = entry.get("id")
            if entry_id is not None:
                if not isinstance(entry_id, str) or not entry_id.strip():
                    _finding(findings, "medium", "HOOK_ID_INVALID", manifest_path, "hook id 必须是非空字符串", f"{event}[{index}]")
                elif entry_id in seen_ids:
                    _finding(findings, "high", "HOOK_ID_DUPLICATE", manifest_path, "hook id 必须全局唯一", f"{event}[{index}]")
                else:
                    seen_ids[entry_id] = f"{event}[{index}]"
            matcher = entry.get("matcher", "*")
            if not isinstance(matcher, (str, dict)):
                _finding(findings, "medium", "HOOK_MATCHER_INVALID", manifest_path, "matcher 必须是字符串或对象", f"{event}[{index}]")
                matcher = "*"
            _audit_hook_items(
                entry.get("hooks"),
                manifest_path,
                findings,
                event,
                str(matcher),
                plugin_root,
                allowed_boundary,
            )


def _audit_mcp_data(
    data: object,
    manifest_path: Path,
    findings: List[Finding],
    plugin_root: Path,
    allowed_boundary: Optional[Path],
) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
        _finding(findings, "high", "MCP_SCHEMA_INVALID", manifest_path, "MCP manifest 缺少对象类型 mcpServers")
        return
    for name, server in data["mcpServers"].items():
        location = f"mcpServers.{name}"
        if not isinstance(server, dict):
            _finding(findings, "high", "MCP_SERVER_INVALID", manifest_path, "MCP server 必须是对象", location)
            continue
        if "url" in server:
            _finding(findings, "medium", "MCP_REMOTE_ENDPOINT", manifest_path, "MCP server 使用远程端点", location)
        command = server.get("command")
        if command is None:
            if "url" not in server:
                _finding(findings, "high", "MCP_COMMAND_MISSING", manifest_path, "MCP server 缺少 command 或 url", location)
        elif not isinstance(command, str) or not command.strip():
            _finding(findings, "high", "MCP_COMMAND_INVALID", manifest_path, "MCP command 必须是非空字符串", location)
        else:
            args_value = server.get("args", [])
            runtime_tokens = [command]
            if isinstance(args_value, list) and all(isinstance(item, str) for item in args_value):
                runtime_tokens.extend(args_value)
            if any(Path(token).name.lower() in RUNTIME_INSTALL_COMMANDS for token in runtime_tokens):
                _finding(findings, "medium", "MCP_RUNTIME_INSTALL", manifest_path, "MCP command 可能触发运行时下载或容器启动", location)
        for field in ("env", "headers"):
            mapping = server.get(field)
            if mapping is None:
                continue
            if not isinstance(mapping, dict):
                _finding(findings, "high", "MCP_SECRET_MAP_INVALID", manifest_path, f"MCP {field} 必须是对象", location)
                continue
            for key, value in mapping.items():
                if (
                    isinstance(key, str)
                    and SENSITIVE_KEY_RE.search(key)
                    and isinstance(value, str)
                    and _is_literal_secret(value)
                ):
                    _finding(
                        findings,
                        "high",
                        "MCP_SECRET_LITERAL",
                        manifest_path,
                        "MCP 配置可能包含硬编码凭据",
                        f"{location}.{key}",
                    )
        args = server.get("args", [])
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            _finding(findings, "high", "MCP_ARGS_INVALID", manifest_path, "MCP args 必须是字符串数组", location)
        elif isinstance(command, str) and command.strip():
            _audit_command_text(
                " ".join([command] + args),
                manifest_path,
                findings,
                location,
                plugin_root=plugin_root,
                allowed_boundary=allowed_boundary,
            )


def audit_manifest(
    manifest_path: Path, strict: bool = False, boundary: Optional[Path] = None
) -> AuditResult:
    input_path = manifest_path
    try:
        manifest_path = manifest_path.resolve(strict=True)
    except (OSError, RuntimeError):
        result = AuditResult(manifest=_display_text(input_path, 500))
        _finding(
            result.findings,
            "critical",
            "PLUGIN_MANIFEST_MISSING",
            input_path,
            "manifest 不存在、不可读或符号链接无法解析",
        )
        return result
    result = AuditResult(manifest=_display_text(manifest_path, 500))
    findings = result.findings
    if boundary is not None:
        try:
            manifest_path.relative_to(boundary.resolve())
        except ValueError:
            _finding(
                findings,
                "critical",
                "PLUGIN_MANIFEST_OUTSIDE_ROOT",
                manifest_path,
                "manifest 解析后越出审计根目录",
            )
            return result
    if manifest_path.name != "plugin.json" or manifest_path.parent.name != ".codex-plugin":
        _finding(findings, "high", "PLUGIN_LAYOUT", manifest_path, "manifest 应位于 .codex-plugin/plugin.json")
        return result
    plugin_root = manifest_path.parent.parent
    data, error = _load_json(manifest_path)
    if error:
        _finding(findings, "critical", "PLUGIN_JSON_INVALID", manifest_path, error)
        return result
    if not isinstance(data, dict):
        _finding(findings, "critical", "PLUGIN_SCHEMA_INVALID", manifest_path, "plugin manifest 顶层必须是对象")
        return result

    for field in ("name", "version", "description"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            _finding(findings, "high", "PLUGIN_FIELD_MISSING", manifest_path, f"缺少非空字段 {field}")
    if isinstance(data.get("name"), str) and not re.fullmatch(r"[A-Za-z0-9._-]+", data["name"]):
        _finding(findings, "high", "PLUGIN_NAME_INVALID", manifest_path, "name 只允许字母、数字、点、下划线和连字符")
    if isinstance(data.get("version"), str) and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,127}", data["version"]):
        _finding(findings, "high", "PLUGIN_VERSION_INVALID", manifest_path, "version 含不受支持或可混淆的字符")
    result.plugin_name = _display_text(data["name"], 128) if isinstance(data.get("name"), str) else None
    result.plugin_version = (
        _display_text(data["version"], 128) if isinstance(data.get("version"), str) else None
    )
    if not isinstance(data.get("license"), str) or not data.get("license", "").strip():
        _finding(findings, "medium", "PLUGIN_LICENSE_MISSING", manifest_path, "manifest 未声明 license")

    if "skills" in data:
        skills_path = _resolve_manifest_reference(
            plugin_root,
            data["skills"],
            "skills",
            findings,
            manifest_path,
            allowed_boundary=boundary,
        )
        if skills_path is not None and not skills_path.is_dir():
            _finding(findings, "high", "PLUGIN_SKILLS_NOT_DIR", manifest_path, "skills 必须指向目录")
    for field in ("assets", "commands", "agents", "rules", "themes"):
        if field in data:
            _audit_reference_values(
                plugin_root, data[field], field, findings, manifest_path, allowed_boundary=boundary
            )
    interface = data.get("interface")
    if isinstance(interface, dict):
        for field in ("logo", "composerIcon", "screenshots"):
            if field in interface:
                _audit_reference_values(
                    plugin_root,
                    interface[field],
                    f"interface.{field}",
                    findings,
                    manifest_path,
                    allowed_boundary=boundary,
                )
    if "apps" in data:
        apps_path = _resolve_manifest_reference(
            plugin_root,
            data["apps"],
            "apps",
            findings,
            manifest_path,
            must_be_file=True,
            allowed_boundary=boundary,
        )
        if apps_path is not None:
            apps_data, apps_error = _load_json(apps_path)
            if apps_error:
                _finding(findings, "high", "PLUGIN_APPS_JSON_INVALID", apps_path, apps_error)
            elif not isinstance(apps_data, dict):
                _finding(findings, "high", "PLUGIN_APPS_SCHEMA_INVALID", apps_path, "apps manifest 顶层必须是对象")

    hooks_value = data.get("hooks")
    if hooks_value is not None:
        if isinstance(hooks_value, dict):
            _audit_hooks_data(hooks_value, manifest_path, findings, plugin_root, boundary)
        elif isinstance(hooks_value, str):
            hooks_path = _resolve_manifest_reference(
                plugin_root,
                hooks_value,
                "hooks",
                findings,
                manifest_path,
                must_be_file=True,
                allowed_boundary=boundary,
            )
            if hooks_path is not None:
                result.hook_manifests.append(_display_text(hooks_path, 500))
                hooks_data, hooks_error = _load_json(hooks_path)
                if hooks_error:
                    _finding(findings, "critical", "HOOKS_JSON_INVALID", hooks_path, hooks_error)
                else:
                    _audit_hooks_data(hooks_data, hooks_path, findings, plugin_root, boundary)
        else:
            _finding(findings, "high", "PLUGIN_HOOKS_INVALID", manifest_path, "hooks 必须是路径或对象")

    mcp_value = data.get("mcpServers")
    if mcp_value is not None:
        if isinstance(mcp_value, dict):
            _audit_mcp_data({"mcpServers": mcp_value}, manifest_path, findings, plugin_root, boundary)
        elif isinstance(mcp_value, str):
            mcp_path = _resolve_manifest_reference(
                plugin_root,
                mcp_value,
                "mcpServers",
                findings,
                manifest_path,
                must_be_file=True,
                allowed_boundary=boundary,
            )
            if mcp_path is not None:
                mcp_data, mcp_error = _load_json(mcp_path)
                if mcp_error:
                    _finding(findings, "critical", "MCP_JSON_INVALID", mcp_path, mcp_error)
                else:
                    _audit_mcp_data(mcp_data, mcp_path, findings, plugin_root, boundary)
        else:
            _finding(findings, "high", "PLUGIN_MCP_INVALID", manifest_path, "mcpServers 必须是路径或对象")

    return result


def _discover_manifests(root: Path) -> List[Path]:
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise DiscoveryError(f"无法解析审计根目录：{error.__class__.__name__}") from error
    if root.is_file():
        return [root]
    manifests: List[Path] = []
    seen = set()

    def add_plugin_root(plugin_root: Path) -> None:
        candidate = plugin_root / ".codex-plugin" / "plugin.json"
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            return
        if resolved in seen or not resolved.is_file():
            return
        if len(seen) >= MAX_DISCOVERED_MANIFESTS:
            raise DiscoveryError(f"plugin manifest 数量超过上限 {MAX_DISCOVERED_MANIFESTS}")
        seen.add(resolved)
        manifests.append(resolved)

    add_plugin_root(root)
    scan_roots = []
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise DiscoveryError(f"无法枚举审计根目录：{error.__class__.__name__}") from error
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        add_plugin_root(child)
        plugins_dir = child / "plugins"
        if plugins_dir.is_dir() and not plugins_dir.is_symlink():
            scan_roots.append(plugins_dir)
    root_plugins = root / "plugins"
    if root_plugins.is_dir() and not root_plugins.is_symlink():
        scan_roots.append(root_plugins)

    visited_dirs = 0

    def raise_walk_error(error: OSError) -> None:
        raise DiscoveryError(f"无法遍历审计目录：{error.__class__.__name__}") from error

    for scan_root in scan_roots:
        for current, dirs, _files in os.walk(scan_root, followlinks=False, onerror=raise_walk_error):
            visited_dirs += 1
            if visited_dirs > MAX_SCANNED_DIRECTORIES:
                raise DiscoveryError(f"审计目录数量超过上限 {MAX_SCANNED_DIRECTORIES}")
            dirs[:] = sorted(
                name
                for name in dirs
                if name not in {".git", "node_modules", "__pycache__", "dist", "build"}
                and not (Path(current) / name).is_symlink()
            )
            add_plugin_root(Path(current))
    return sorted(manifests)


def _should_fail(findings: Iterable[Finding], strict: bool) -> bool:
    threshold = 2 if strict else 3
    return any(SEVERITY_ORDER[finding.severity] >= threshold for finding in findings)


def _print_text(results: Sequence[AuditResult], strict: bool) -> None:
    total = sum(len(result.findings) for result in results)
    print(f"plugin-audit: manifests={len(results)} findings={total} strict={str(strict).lower()}")
    for result in results:
        identity = _display_text(result.plugin_name or "<unknown>", 128)
        if result.plugin_version:
            identity += f"@{_display_text(result.plugin_version, 128)}"
        print(f"\n[{identity}] {_display_text(result.manifest, 500)}")
        if not result.findings:
            print("  PASS")
            continue
        for finding in sorted(result.findings, key=lambda item: (-SEVERITY_ORDER[item.severity], item.code)):
            location = f" {_display_text(finding.location)}" if finding.location else ""
            print(
                f"  {finding.severity.upper():8} {finding.code}{location}: "
                f"{finding.message} ({_display_text(finding.path, 500)})"
            )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Statically audit Codex plugin and hook manifests.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--manifest", type=Path, help="audit one .codex-plugin/plugin.json")
    source.add_argument("--root", type=Path, help="recursively find plugin manifests under a directory")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true", help="also fail on medium findings")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    root = args.manifest or args.root or Path.cwd()
    try:
        manifests = _discover_manifests(root)
    except DiscoveryError as error:
        print(f"plugin-audit: {error}", file=sys.stderr)
        return 2
    if not manifests:
        print(f"plugin-audit: no plugin manifests found under {root}", file=sys.stderr)
        return 2
    try:
        boundary = args.root.resolve(strict=True) if args.root is not None else None
    except (OSError, RuntimeError) as error:
        print(f"plugin-audit: 无法解析审计根目录：{error.__class__.__name__}", file=sys.stderr)
        return 2
    results = [audit_manifest(path, strict=args.strict, boundary=boundary) for path in manifests]
    if args.format == "json":
        payload = {
            "schema_version": "1",
            "strict": args.strict,
            "results": [
                {
                    **asdict(result),
                    "findings": [asdict(finding) for finding in result.findings],
                }
                for result in results
            ],
            "summary": {
                "manifests": len(results),
                "findings": sum(len(result.findings) for result in results),
                "failed": any(_should_fail(result.findings, args.strict) for result in results),
            },
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
        sys.stdout.write("\n")
    else:
        _print_text(results, args.strict)
    return 1 if any(_should_fail(result.findings, args.strict) for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
