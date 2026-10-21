#!/usr/bin/env python3
"""Discover external SKILL.md files below refer/git-rep/**/*skills safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Optional


IGNORED_DIRS = {".git", "__pycache__", "node_modules", "site-packages", "venv", ".venv"}
DESCRIPTION_LIMIT = 420
FRONTMATTER_LIMIT = 64 * 1024


class DiscoveryError(RuntimeError):
    """Raised for invalid roots, paths, or discovery arguments."""


@dataclass(frozen=True)
class SkillRecord:
    name: str
    description: str
    path: Path
    resolved_path: Path
    source_repo: str
    lifecycle: str
    kind: str
    directory_name: str


def _default_configure_root() -> Path:
    configured = os.environ.get("CONFIGURE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_skills_dir_name(name: str) -> bool:
    return name == "skills" or name.endswith("skills")


def _resolve_root(configure_root: Path) -> tuple[Path, Path]:
    try:
        root = configure_root.expanduser().resolve(strict=True)
        refer_root = (root / "refer" / "git-rep").resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise DiscoveryError(f"配置根或参考根不可解析: {configure_root}: {error}") from error
    if not refer_root.is_dir():
        raise DiscoveryError(f"参考目录不存在: {refer_root}")
    return root, refer_root


def _iter_skills_roots(refer_root: Path, warnings: list[str]) -> Iterable[Path]:
    roots: set[Path] = set()

    def _walk_error(error: OSError) -> None:
        warnings.append(f"遍历参考目录失败 {getattr(error, 'filename', refer_root)}: {error}")

    for current_raw, dirnames, _filenames in os.walk(
        refer_root,
        followlinks=False,
        onerror=_walk_error,
    ):
        current = Path(current_raw)
        for dirname in dirnames:
            candidate = current / dirname
            if current != refer_root and _is_skills_dir_name(dirname):
                try:
                    if candidate.is_dir():
                        roots.add(candidate.absolute())
                    elif candidate.is_symlink():
                        warnings.append(f"跳过不可解析的 skills 链接 {candidate}")
                except OSError as error:
                    warnings.append(f"跳过不可访问的 skills 目录 {candidate}: {error}")
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in IGNORED_DIRS and not (current / dirname).is_symlink()
        ]
    return sorted(roots, key=lambda item: str(item))


def _iter_skill_files(skills_root: Path, refer_root: Path, warnings: list[str]) -> Iterable[Path]:
    seen_dirs: set[tuple[int, int]] = set()

    def _walk(directory: Path) -> Iterable[Path]:
        try:
            real_directory = directory.resolve(strict=True)
            stat = directory.stat()
        except (OSError, RuntimeError) as error:
            warnings.append(f"跳过不可解析技能目录 {directory}: {error}")
            return
        if not _is_within(real_directory, refer_root):
            warnings.append(f"跳过越出参考根技能目录 {directory} -> {real_directory}")
            return
        key = (stat.st_dev, stat.st_ino)
        if key in seen_dirs:
            if directory.is_symlink():
                warnings.append(f"跳过重复或循环技能目录链接 {directory} -> {real_directory}")
            return
        seen_dirs.add(key)

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as error:
            warnings.append(f"跳过不可访问技能目录 {directory}: {error}")
            return
        for child in children:
            if child.name in IGNORED_DIRS:
                continue
            if child.name == "SKILL.md":
                try:
                    resolved = child.resolve(strict=True)
                    if not child.is_file():
                        warnings.append(f"跳过非文件 SKILL.md {child}")
                        continue
                    if not _is_within(resolved, refer_root):
                        warnings.append(f"跳过越出参考根的 SKILL.md {child} -> {resolved}")
                        continue
                    yield child.absolute()
                except (OSError, RuntimeError) as error:
                    warnings.append(f"跳过不可解析 SKILL.md {child}: {error}")
                    continue
                continue
            if child.is_symlink() and not child.exists():
                warnings.append(f"跳过断链技能路径 {child}")
                continue
            try:
                if child.is_dir():
                    yield from _walk(child)
            except OSError as error:
                warnings.append(f"跳过不可访问技能路径 {child}: {error}")
                continue

    yield from _walk(skills_root)


def _strip_yaml_comment(value: str) -> str:
    quote: Optional[str] = None
    escaped = False
    index = 0
    while index < len(value):
        char = value[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
        index += 1
    return value.rstrip()


def _normalize_scalar(value: str) -> str:
    value = _strip_yaml_comment(value.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        value = value[1:-1].replace(quote + quote, quote)
    return value.strip()


def _descriptor_path(fd: int) -> Path:
    for descriptor_root in (Path("/proc/self/fd"), Path("/dev/fd")):
        descriptor = descriptor_root / str(fd)
        try:
            target = os.readlink(descriptor)
        except OSError:
            continue
        if target.endswith(" (deleted)"):
            target = target[: -len(" (deleted)")]
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = Path.cwd() / target_path
        return target_path.resolve(strict=False)
    raise OSError("当前平台无法验证已打开文件的真实路径")


def _sanitize_text(value: object) -> str:
    sanitized: list[str] = []
    for char in str(value):
        if char in "\r\n\t":
            sanitized.append(" ")
        elif unicodedata.category(char) in {"Cc", "Cf"}:
            sanitized.append(" ")
        else:
            sanitized.append(char)
    return "".join(sanitized)


def _read_frontmatter(path: Path, refer_root: Path) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    fd = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            warnings.append(f"frontmatter 目标不是普通文件: {path}")
            return path.parent.name, "", warnings
        opened_path = _descriptor_path(fd)
        if not _is_within(opened_path, refer_root):
            warnings.append(f"frontmatter 读取越界，拒绝读取: {path} -> {opened_path}")
            return path.parent.name, "", warnings
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace", closefd=True) as handle:
            fd = -1
            text = handle.read(FRONTMATTER_LIMIT)
    except (OSError, RuntimeError) as error:
        warnings.append(f"frontmatter 读取失败 {path}: {error}")
        return path.parent.name, "", warnings
    finally:
        if fd >= 0:
            os.close(fd)

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        warnings.append(f"缺少 frontmatter，使用目录名作为技能名: {path}")
        return path.parent.name, "", warnings

    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        warnings.append(f"frontmatter 未闭合，使用目录名作为技能名: {path}")
        return path.parent.name, "", warnings

    values: dict[str, str] = {}
    index = 1
    while index < closing:
        line = lines[index]
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            index += 1
            continue
        key, raw_value = match.groups()
        if key not in {"name", "description"}:
            index += 1
            continue
        if raw_value.strip() in {"|", "|-", "|+", ">", ">-", ">+"}:
            block: list[str] = []
            index += 1
            while index < closing:
                block_line = lines[index]
                if block_line and not block_line[:1].isspace():
                    break
                block.append(block_line.strip())
                index += 1
            values[key] = " ".join(part for part in block if part).strip()
            continue
        values[key] = _normalize_scalar(raw_value)
        index += 1

    name = values.get("name", "").strip()
    if not name:
        warnings.append(f"frontmatter 缺少 name，使用目录名作为技能名: {path}")
        name = path.parent.name
    elif name == "<name>":
        warnings.append(f"frontmatter 使用模板 name=<name>，回退目录名: {path}")
        name = path.parent.name
    description = values.get("description", "").strip()
    return _sanitize_text(name).strip(), _sanitize_text(description).strip(), warnings


def _classify(path: Path, refer_root: Path) -> tuple[str, str, str]:
    relative = path.relative_to(refer_root)
    parts = relative.parts
    source_repo = parts[0] if parts else "unknown"
    if "deprecated" in parts:
        lifecycle = "deprecated"
    elif "in-progress" in parts:
        lifecycle = "in-progress"
    else:
        lifecycle = "active"
    if "plugins" in parts:
        kind = "plugin"
    elif sum(1 for part in parts[1:] if _is_skills_dir_name(part)) > 1:
        kind = "nested"
    else:
        kind = "standard"
    return source_repo, lifecycle, kind


def _compact(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    text = " ".join(_sanitize_text(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _discover(refer_root: Path) -> tuple[list[SkillRecord], list[str]]:
    by_real_path: dict[Path, Path] = {}
    warnings: list[str] = []
    skills_roots = list(_iter_skills_roots(refer_root, warnings))
    if not skills_roots:
        warnings.append(f"未发现任何名称以 skills 结尾的技能目录: {refer_root}")
    for skills_root in skills_roots:
        for skill_file in _iter_skill_files(skills_root, refer_root, warnings):
            try:
                real_path = skill_file.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                warnings.append(f"跳过不可解析路径 {skill_file}: {error}")
                continue
            current = by_real_path.get(real_path)
            if current is None or len(skill_file.parts) < len(current.parts):
                by_real_path[real_path] = skill_file

    records: list[SkillRecord] = []
    for skill_file in sorted(by_real_path.values(), key=lambda item: str(item)):
        try:
            resolved_path = skill_file.resolve(strict=True)
            source_repo, lifecycle, kind = _classify(resolved_path, refer_root)
        except (OSError, RuntimeError, ValueError) as error:
            warnings.append(f"跳过无法分类路径 {skill_file}: {error}")
            continue
        name, description, frontmatter_warnings = _read_frontmatter(skill_file, refer_root)
        warnings.extend(frontmatter_warnings)
        records.append(
            SkillRecord(
                name=name,
                description=description,
                path=skill_file,
                resolved_path=resolved_path,
                source_repo=source_repo,
                lifecycle=lifecycle,
                kind=kind,
                directory_name=skill_file.parent.name,
            )
        )
    records.sort(key=lambda item: (item.name.casefold(), item.path.as_posix()))
    warnings = list(dict.fromkeys(_sanitize_text(warning) for warning in warnings))
    return records, warnings


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+", value.casefold()) if token]


def _match_score(record: SkillRecord, query: str) -> int:
    normalized_query = " ".join(query.casefold().split())
    if not normalized_query:
        return 0
    name = record.name.casefold()
    directory_name = record.directory_name.casefold()
    description = record.description.casefold()
    path = record.path.as_posix().casefold()
    query_tokens = list(dict.fromkeys(_tokens(normalized_query)))

    score = 0
    if normalized_query == name or normalized_query == directory_name:
        score += 10000
    elif normalized_query in name or normalized_query in directory_name:
        score += 5000
    if normalized_query in description:
        score += 1800
    if normalized_query in path:
        score += 500

    matched_name = 0
    matched_description = 0
    all_terms_present = True
    for token in query_tokens:
        in_name = token in name or token in directory_name
        in_description = token in description
        in_path = token in path
        if in_name:
            matched_name += 1
        if in_description:
            matched_description += 1
        if in_name or in_description or in_path:
            score += 40 if in_path and not (in_name or in_description) else 0
        else:
            all_terms_present = False
    score += matched_name * 320
    score += matched_description * 90
    if query_tokens and all_terms_present:
        score += 700
    return score


def _lifecycle_rank(record: SkillRecord) -> int:
    return {"active": 0, "in-progress": 1, "deprecated": 2}.get(record.lifecycle, 3)


def _kind_rank(record: SkillRecord) -> int:
    return {"standard": 0, "nested": 1, "plugin": 2}.get(record.kind, 3)


def _selection_key(record: SkillRecord) -> tuple[int, int, int, str, str]:
    return (
        _lifecycle_rank(record),
        _kind_rank(record),
        len(record.path.parts),
        record.name.casefold(),
        record.path.as_posix(),
    )


def _record_payload(record: SkillRecord, score: int) -> dict[str, object]:
    return {
        "name": _sanitize_text(record.name),
        "directory_name": _sanitize_text(record.directory_name),
        "description": _compact(record.description),
        "path": _sanitize_text(record.path),
        "resolved_path": _sanitize_text(record.resolved_path),
        "source_repo": _sanitize_text(record.source_repo),
        "lifecycle": _sanitize_text(record.lifecycle),
        "kind": _sanitize_text(record.kind),
        "score": score,
    }


def _as_tsv(records: list[tuple[SkillRecord, int]]) -> str:
    def _tsv_field(value: object) -> str:
        return _sanitize_text(value)

    lines = ["score\tname\tlifecycle\trepo\tpath\tdescription"]
    for record, score in records:
        fields = (
            score,
            record.name,
            record.lifecycle,
            record.source_repo,
            record.path,
            _compact(record.description, 220),
        )
        lines.append("\t".join(_tsv_field(field) for field in fields))
    return "\n".join(lines)


def _parse_nonnegative(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是整数") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须大于等于 0")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="发现 refer/git-rep/**/*skills 中的 SKILL.md，并支持名称或语义关键词筛选。",
    )
    parser.add_argument("--root", type=Path, default=_default_configure_root(), help="configure 仓库根目录")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--query", default="", help="名称、描述和路径的关键词查询")
    selector.add_argument("--name", help="按 frontmatter name 或技能目录名精确筛选")
    selector.add_argument("--path", type=Path, help="精确检查 SKILL.md 或技能目录")
    parser.add_argument("--limit", type=_parse_nonnegative, default=20, help="最多返回条数；0 表示全部")
    parser.add_argument("--format", choices=("json", "tsv"), default="json", help="输出格式")
    return parser


def _select_records(
    records: list[SkillRecord],
    *,
    query: str,
    name: Optional[str],
    exact_path: Optional[Path],
    refer_root: Path,
) -> list[tuple[SkillRecord, int]]:
    if exact_path is not None:
        candidate = exact_path.expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = Path(os.path.abspath(candidate))
        if candidate.is_dir():
            candidate = candidate / "SKILL.md"
        displayed_parts = candidate.parts
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise DiscoveryError(f"路径不存在或不可解析: {candidate}") from error
        if not _is_within(resolved, refer_root):
            raise DiscoveryError(f"路径越出参考根 {refer_root}: {candidate}")
        if not any(_is_skills_dir_name(part) for part in displayed_parts) and not any(
            _is_skills_dir_name(part) for part in resolved.parts
        ):
            raise DiscoveryError(f"路径不在 refer/git-rep/**/*skills 下: {candidate}")
        matches: list[tuple[SkillRecord, int]] = []
        for record in records:
            if record.resolved_path != resolved:
                continue
            source_repo, lifecycle, kind = _classify(resolved, refer_root)
            matches.append(
                (
                    replace(
                        record,
                        path=candidate,
                        source_repo=source_repo,
                        lifecycle=lifecycle,
                        kind=kind,
                        directory_name=candidate.parent.name,
                    ),
                    20000,
                )
            )
        if not matches:
            raise DiscoveryError(f"未发现 SKILL.md 候选: {candidate}")
        return matches

    if name is not None:
        normalized = name.casefold()
        matches = [
            (record, 10000)
            for record in records
            if record.name.casefold() == normalized
            or record.directory_name.casefold() == normalized
        ]
        matches.sort(key=lambda item: _selection_key(item[0]))
        return matches

    scored = [(record, _match_score(record, query)) for record in records]
    if query:
        scored = [item for item in scored if item[1] > 0]
    scored.sort(
        key=lambda item: (-item[1], *_selection_key(item[0]))
    )
    return scored


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        root, refer_root = _resolve_root(args.root)
        records, warnings = _discover(refer_root)
        selected = _select_records(
            records,
            query=args.query,
            name=args.name,
            exact_path=args.path,
            refer_root=refer_root,
        )
    except DiscoveryError as error:
        print(f"conf-refer-skill: {error}", file=sys.stderr)
        return 2

    if args.limit:
        selected = selected[: args.limit]
    name_counts = Counter(record.name for record in records)
    selected_names = {record.name for record, _score in selected}
    duplicate_names = sorted(name for name in selected_names if name_counts[name] > 1)
    global_duplicate_name_count = sum(1 for count in name_counts.values() if count > 1)

    if args.format == "tsv":
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        print(_as_tsv(selected))
        return 0

    payload = {
        "configure_root": _sanitize_text(root),
        "refer_root": _sanitize_text(refer_root),
        "query": _sanitize_text(args.query),
        "name_filter": _sanitize_text(args.name) if args.name else None,
        "path_filter": _sanitize_text(args.path) if args.path else None,
        "candidate_count": len(records),
        "returned_count": len(selected),
        "duplicate_names": duplicate_names,
        "global_duplicate_name_count": global_duplicate_name_count,
        "warnings": warnings,
        "matches": [_record_payload(record, score) for record, score in selected],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
