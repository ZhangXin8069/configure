#!/usr/bin/env python3
"""Inventory newly added Git content for provenance-aware absorption."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DEFAULT_SCAN_BYTES = 4 * 1024 * 1024
FOREIGN_PATH_RE = re.compile(
    r"(^|/)(refer|reference|vendor|vendored|third[-_]?party|external|extern|upstream|submodules?|deps?)(/|$)",
    re.IGNORECASE,
)
LICENSE_RE = re.compile(
    r"(^|/)(licenses?|licences?)(/|$)|"
    r"(^|/)(license|licence|copying|copyright|notice)([-.][a-z0-9.+-]+)?$|"
    r"[-.](license|licence)$",
    re.IGNORECASE,
)
PROVENANCE_RE = re.compile(
    r"\b(upstream|forked from|vendored from|generated from|copied from|original source|source repository)\b|"
    r"\bSPDX-License-Identifier\s*:|\bCopyright\s+\(c\)",
    re.IGNORECASE,
)
SECRET_RE = re.compile(
    r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*(?:['\"])?[^\s'\"#]{8,}(?:['\"])?",
    re.IGNORECASE,
)
DYNAMIC_EXEC_RE = re.compile(
    r"\b(eval|exec)\s*\(|\bos\.system\s*\(|\bsubprocess\.(?:run|Popen|call)\s*\(|"
    r"\bchild_process\.(?:exec|spawn)\s*\(|curl\b[^\n|]{0,160}\|\s*(?:sh|bash)\b|"
    r"wget\b[^\n|]{0,160}\|\s*(?:sh|bash)\b",
    re.IGNORECASE,
)
DESTRUCTIVE_RE = re.compile(
    r"\brm\s+-[a-z]*r[a-z]*f|\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[a-z]*[df]|"
    r"\bmkfs(?:\.|\s)|\bdd\s+if=|\bshred\b|\btruncate\s+-s\s*0\b",
    re.IGNORECASE,
)
NETWORK_RE = re.compile(
    r"\b(?:requests\.(?:get|post|put|delete)|urllib\.request|urlopen|fetch)\s*\(|"
    r"\b(?:curl|wget)\b|\bhttps?://",
    re.IGNORECASE,
)
MANIFEST_NAMES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "pyproject.toml",
    "requirements.txt", "setup.py", "setup.cfg", "poetry.lock", "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum", "pom.xml", "build.gradle", "Gemfile", "Gemfile.lock", "composer.json",
}
BINARY_SUFFIXES = {
    ".7z", ".a", ".bin", ".bz2", ".class", ".dll", ".dylib", ".exe", ".gif", ".gz",
    ".ico", ".jar", ".jpeg", ".jpg", ".o", ".pdf", ".png", ".pyc", ".so", ".tar",
    ".tgz", ".webp", ".whl", ".xz", ".zip",
}


class InventoryError(RuntimeError):
    """Raised for deterministic inventory failures."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_git(root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode != 0:
        raise InventoryError(process.stderr.strip() or f"git {' '.join(args)} failed")
    return process


def find_git_root(start: Path) -> Path:
    process = run_git(start, ["rev-parse", "--show-toplevel"])
    return Path(process.stdout.strip()).resolve()


def git_has_head(root: Path) -> bool:
    return run_git(root, ["rev-parse", "--verify", "HEAD"], check=False).returncode == 0


def resolve_base(root: Path, requested: str) -> str:
    if requested != "auto":
        resolved = run_git(root, ["rev-parse", "--verify", f"{requested}^{{commit}}"]).stdout.strip()
        return resolved
    upstream = run_git(
        root,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    )
    if upstream.returncode == 0 and upstream.stdout.strip():
        merge_base = run_git(root, ["merge-base", "HEAD", upstream.stdout.strip()], check=False)
        if merge_base.returncode == 0:
            return merge_base.stdout.strip()
    if git_has_head(root):
        parent = run_git(root, ["rev-parse", "--verify", "HEAD^"], check=False)
        if parent.returncode == 0:
            return parent.stdout.strip()
    return EMPTY_TREE


def split_nul(output: str) -> list[str]:
    return [item for item in output.split("\0") if item]


def added_since(root: Path, base: str) -> set[str]:
    if not git_has_head(root):
        return set()
    revision_range = f"{base}..HEAD" if base == EMPTY_TREE else f"{base}...HEAD"
    output = run_git(root, ["diff", "--name-only", "--diff-filter=AT", "-z", revision_range]).stdout
    return set(split_nul(output))


def staged_additions(root: Path) -> set[str]:
    output = run_git(root, ["diff", "--cached", "--name-only", "--diff-filter=AT", "-z"]).stdout
    return set(split_nul(output))


def untracked_additions(root: Path, *, include_ignored: bool) -> set[str]:
    output = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).stdout
    if include_ignored:
        output += run_git(root, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"]).stdout
    return set(split_nul(output))


def git_bytes(root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode != 0:
        error = process.stderr.decode("utf-8", errors="replace").strip()
        raise InventoryError(error or f"git {' '.join(args)} failed")
    return process


def parse_git_entry(raw: bytes) -> dict[str, str] | None:
    first = raw.split(b"\0", 1)[0]
    if not first:
        return None
    metadata, separator, name = first.partition(b"\t")
    if not separator:
        return None
    fields = metadata.decode("ascii", errors="replace").split()
    if len(fields) < 2:
        return None
    object_id = fields[2] if len(fields) >= 3 and fields[1] in {"blob", "commit", "tree"} else fields[1]
    return {
        "mode": fields[0],
        "oid": object_id,
        "path": name.decode("utf-8", errors="surrogateescape"),
    }


def index_entry(root: Path, path: str) -> dict[str, str] | None:
    return parse_git_entry(git_bytes(root, ["ls-files", "--stage", "-z", "--", path], check=False).stdout)


def commit_entry(root: Path, path: str) -> dict[str, str] | None:
    return parse_git_entry(git_bytes(root, ["ls-tree", "-z", "HEAD", "--", path], check=False).stdout)


def read_git_blob_limited(root: Path, oid: str, max_scan_bytes: int) -> tuple[str, bytes, int]:
    size_output = git_bytes(root, ["cat-file", "-s", oid]).stdout.decode("ascii", errors="replace").strip()
    try:
        size = int(size_output)
    except ValueError as error:
        raise InventoryError(f"无法读取 Git blob 大小: {oid}") from error
    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "blob", oid],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        raise InventoryError(f"无法启动 Git blob 读取: {oid}")
    digest = hashlib.sha256()
    prefix = bytearray()
    with process.stdout, process.stderr:
        while chunk := process.stdout.read(1024 * 1024):
            digest.update(chunk)
            if len(prefix) < max_scan_bytes:
                prefix.extend(chunk[: max_scan_bytes - len(prefix)])
        error = process.stderr.read().decode("utf-8", errors="replace").strip()
    return_code = process.wait()
    if return_code != 0:
        raise InventoryError(error or f"git cat-file blob {oid} failed")
    return digest.hexdigest(), bytes(prefix), size


def read_worktree_version(root: Path, path: str, max_scan_bytes: int) -> dict[str, Any] | None:
    absolute = root / path
    try:
        stat = absolute.lstat()
    except FileNotFoundError:
        return None
    if absolute.is_symlink():
        data = os.readlink(absolute).encode("utf-8", errors="surrogateescape")
        return {
            "source": "symlink",
            "mode": "120000",
            "object_id": None,
            "sha256": hashlib.sha256(data).hexdigest(),
            "data": data[:max_scan_bytes],
            "size": len(data),
            "is_symlink": True,
        }
    if absolute.is_file():
        digest = hashlib.sha256()
        prefix = bytearray()
        with absolute.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                if len(prefix) < max_scan_bytes:
                    prefix.extend(chunk[: max_scan_bytes - len(prefix)])
        return {
            "source": "worktree",
            "mode": "100755" if stat.st_mode & 0o111 else "100644",
            "object_id": None,
            "sha256": digest.hexdigest(),
            "data": bytes(prefix),
            "size": stat.st_size,
            "is_symlink": False,
        }
    return None


def read_git_version(
    root: Path,
    path: str,
    *,
    scope: str,
    max_scan_bytes: int,
) -> dict[str, Any] | None:
    entry = index_entry(root, path) if scope == "staged" else commit_entry(root, path)
    if not entry:
        return None
    if entry["mode"] == "160000":
        return {
            "source": "gitlink",
            "mode": entry["mode"],
            "object_id": entry["oid"],
            "sha256": None,
            "data": b"",
            "size": 0,
            "is_symlink": False,
        }
    digest, data, size = read_git_blob_limited(root, entry["oid"], max_scan_bytes)
    return {
        "source": "index" if scope == "staged" else "commit",
        "mode": entry["mode"],
        "object_id": entry["oid"],
        "sha256": digest,
        "data": data,
        "size": size,
        "is_symlink": entry["mode"] == "120000",
    }


def text_prefix(data: bytes) -> tuple[str | None, bool]:
    if b"\0" in data[:8192]:
        return None, True
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), False


def line_hits(pattern: re.Pattern[str], text: str) -> tuple[list[int], int]:
    lines: list[int] = []
    count = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            count += 1
            if len(lines) < 20:
                lines.append(number)
    return lines, count


def classify_language(path: str, binary: bool) -> str:
    if binary:
        return "binary"
    suffix = Path(path).suffix.casefold()
    return {
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".h": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".tex": "tex",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
    }.get(suffix, "text")


def top_group(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if len(parts) > 1 else "."


def analyze_candidate(
    path: str,
    scope: str,
    version: dict[str, Any],
) -> dict[str, Any]:
    mode = str(version.get("mode") or "")
    source = str(version.get("source") or "unknown")
    is_gitlink = mode == "160000"
    is_symlink = bool(version.get("is_symlink"))
    scan = bytes(version.get("data") or b"")
    size = int(version.get("size") or 0)
    digest = version.get("sha256")
    object_id = version.get("object_id")
    text, binary = text_prefix(scan)
    line_count = len(text.splitlines()) if text is not None else 0
    scan_truncated = bool(size and len(scan) < size and not is_gitlink)

    path_foreign = bool(FOREIGN_PATH_RE.search(path))
    license_file = bool(LICENSE_RE.search(path))
    provenance_lines, provenance_count = line_hits(PROVENANCE_RE, text) if text else ([], 0)
    secret_lines, secret_count = line_hits(SECRET_RE, text) if text else ([], 0)
    exec_lines, exec_count = line_hits(DYNAMIC_EXEC_RE, text) if text else ([], 0)
    destructive_lines, destructive_count = line_hits(DESTRUCTIVE_RE, text) if text else ([], 0)
    network_lines, network_count = line_hits(NETWORK_RE, text) if text else ([], 0)

    if is_gitlink:
        origin_hint = "gitlink"
    elif path_foreign or license_file or provenance_lines:
        origin_hint = "likely-foreign"
    else:
        origin_hint = "unknown"

    risk_signals: list[dict[str, Any]] = []
    if is_gitlink:
        risk_signals.append(
            {
                "type": "gitlink",
                "object_id": object_id,
                "detail": "submodule pointer requires separate provenance audit",
            }
        )
    if is_symlink:
        risk_signals.append(
            {
                "type": "symlink",
                "target_sha256": digest,
                "target_bytes": size,
                "detail": "do not follow the link while analyzing untrusted content",
            }
        )
    if binary:
        risk_signals.append({"type": "binary", "detail": "binary content was hashed but not executed or fully decoded"})
    if scan_truncated:
        risk_signals.append(
            {
                "type": "scan-truncated",
                "detail": f"only the first {len(scan)} of {size} bytes were pattern-scanned",
            }
        )
    if mode == "100755":
        risk_signals.append({"type": "executable-bit", "detail": "file is executable in Git"})
    if secret_count:
        risk_signals.append(
            {
                "type": "secret-like",
                "lines": secret_lines,
                "hit_count": secret_count,
                "detail": "values intentionally redacted",
            }
        )
    if exec_count:
        risk_signals.append({"type": "dynamic-execution", "lines": exec_lines, "hit_count": exec_count})
    if destructive_count:
        risk_signals.append(
            {"type": "destructive-command", "lines": destructive_lines, "hit_count": destructive_count}
        )
    if network_count:
        risk_signals.append({"type": "network-access", "lines": network_lines, "hit_count": network_count})
    if Path(path).suffix.casefold() in BINARY_SUFFIXES:
        risk_signals.append({"type": "archive-or-binary-suffix", "detail": Path(path).suffix.casefold()})

    provenance_signals: list[dict[str, Any]] = []
    if path_foreign:
        provenance_signals.append({"type": "foreign-path", "value": path})
    if license_file:
        provenance_signals.append({"type": "license-file", "value": Path(path).name})
    if provenance_count:
        provenance_signals.append(
            {"type": "provenance-marker", "lines": provenance_lines, "hit_count": provenance_count}
        )
    if Path(path).name in MANIFEST_NAMES:
        provenance_signals.append({"type": "dependency-manifest", "value": Path(path).name})

    return {
        "id": hashlib.sha256(
            f"{path}\0{scope}\0{source}\0{digest or object_id or ''}".encode(
                "utf-8",
                errors="surrogateescape",
            )
        ).hexdigest()[:12],
        "path": path,
        "top_group": top_group(path),
        "scope": scope,
        "scopes": [scope],
        "git_mode": mode,
        "source": source,
        "object_id": object_id,
        "size_bytes": size,
        "sha256": digest,
        "language": "gitlink" if is_gitlink else ("symlink" if is_symlink else classify_language(path, binary)),
        "binary": binary,
        "line_count": line_count,
        "scan_bytes": len(scan),
        "scan_truncated": scan_truncated,
        "origin_hint": origin_hint,
        "provenance_signals": provenance_signals,
        "risk_signals": risk_signals,
    }


def build_inventory(
    root: Path,
    *,
    base_requested: str,
    scope: str,
    max_scan_bytes: int,
    include_ignored: bool = False,
) -> dict[str, Any]:
    base = resolve_base(root, base_requested)
    candidates: list[dict[str, Any]] = []
    candidate_versions: list[tuple[str, str, dict[str, Any]]] = []
    commit_paths: set[str] = set()
    staged_paths: set[str] = set()
    if scope in {"all", "commits"}:
        commit_paths = added_since(root, base)
        for path in commit_paths:
            version = read_git_version(root, path, scope="commits", max_scan_bytes=max_scan_bytes)
            if version:
                candidate_versions.append(("commits", path, version))
    if scope in {"all", "worktree"}:
        staged_paths = staged_additions(root)
        for path in staged_paths:
            version = read_git_version(root, path, scope="staged", max_scan_bytes=max_scan_bytes)
            if version:
                candidate_versions.append(("staged", path, version))
        for path in untracked_additions(root, include_ignored=include_ignored):
            version = read_worktree_version(root, path, max_scan_bytes)
            if version:
                candidate_versions.append(("untracked", path, version))

        baseline_paths = commit_paths | staged_paths
        for path in sorted(baseline_paths):
            current = read_worktree_version(root, path, max_scan_bytes)
            baseline_scope = "staged" if path in staged_paths else "commits"
            baseline = read_git_version(root, path, scope=baseline_scope, max_scan_bytes=max_scan_bytes)
            if current and baseline and (
                current["sha256"] != baseline.get("sha256") or current["mode"] != baseline.get("mode")
            ):
                candidate_versions.append(("worktree-diff", path, current))

    for candidate_scope, path, version in sorted(
        candidate_versions,
        key=lambda item: (item[1], item[0], str(item[2].get("source")), str(item[2].get("sha256"))),
    ):
        candidates.append(
            analyze_candidate(
                path,
                candidate_scope,
                version,
            )
        )
    origin_counts = Counter(item["origin_hint"] for item in candidates)
    risk_counts = Counter(signal["type"] for item in candidates for signal in item["risk_signals"])
    groups = Counter(item["top_group"] for item in candidates)
    sources = Counter(item["source"] for item in candidates)
    head_process = run_git(root, ["rev-parse", "HEAD"], check=False)
    head = head_process.stdout.strip() if head_process.returncode == 0 else None
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "root": str(root),
        "head": head,
        "base": base,
        "scope": scope,
        "include_ignored": include_ignored,
        "candidate_count": len(candidates),
        "summary": {
            "by_origin": dict(sorted(origin_counts.items())),
            "by_risk": dict(sorted(risk_counts.items())),
            "by_top_group": dict(sorted(groups.items())),
            "by_source": dict(sorted(sources.items())),
            "binary_or_link_count": sum(1 for item in candidates if item["binary"] or item["git_mode"] == "160000" or any(
                signal["type"] == "symlink" for signal in item["risk_signals"]
            )),
        },
        "candidates": candidates,
        "coverage_rule": "Every candidate id must be assigned exactly one disposition: keep, adapt, reference-only, or reject.",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory newly added Git files for provenance-aware external-content absorption.",
    )
    parser.add_argument("--version", action="version", version="absorb-inventory 1.0")
    parser.add_argument("--root", default=".", help="path inside the target Git worktree")
    parser.add_argument(
        "--base",
        default="auto",
        help="commit/ref used for committed additions; auto prefers upstream merge-base, then HEAD^",
    )
    parser.add_argument("--scope", choices=("all", "commits", "worktree"), default="all")
    parser.add_argument("--max-scan-bytes", type=int, default=DEFAULT_SCAN_BYTES)
    parser.add_argument(
        "--include-ignored",
        action="store_true",
        help="include ignored untracked files; disabled by default to avoid dependency/build caches",
    )
    parser.add_argument("--output", help="optional JSON manifest path")
    parser.add_argument("--quiet", action="store_true", help="suppress JSON on stdout when writing --output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_scan_bytes <= 0:
        print("absorb-inventory: --max-scan-bytes must be positive", file=sys.stderr)
        return 2
    try:
        root = find_git_root(Path(args.root).expanduser().resolve())
        payload = build_inventory(
            root,
            base_requested=args.base,
            scope=args.scope,
            max_scan_bytes=args.max_scan_bytes,
            include_ignored=args.include_ignored,
        )
        if args.output:
            output = Path(args.output).expanduser().resolve()
            if output != root and root not in output.parents:
                raise InventoryError(f"输出路径必须位于目标 Git 工作树内: {output}")
            write_json(output, payload)
        if not args.quiet:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (InventoryError, OSError) as error:
        print(f"absorb-inventory: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
