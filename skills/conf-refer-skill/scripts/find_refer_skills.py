#!/usr/bin/env python3
"""Discover external SKILL.md files below refer/git-rep/**/skills safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable


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


def default_configure_root() -> Path:
    configured = os.environ.get("CONFIGURE_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3]


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_root(configure_root: Path) -> tuple[Path, Path]:
    root = configure_root.expanduser().resolve()
    refer_root = (root / "refer" / "git-rep").resolve()
    if not refer_root.is_dir():
        raise DiscoveryError(f"参考目录不存在: {refer_root}")
    return root, refer_root


def iter_skills_roots(refer_root: Path, warnings: list[str]) -> Iterable[Path]:
    roots: set[Path] = set()
    for current_raw, dirnames, _filenames in os.walk(refer_root, followlinks=False):
        current = Path(current_raw)
        for dirname in dirnames:
            candidate = current / dirname
            if dirname == "skills":
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


def iter_skill_files(skills_root: Path, refer_root: Path, warnings: list[str]) -> Iterable[Path]:
    seen_dirs: set[tuple[int, int]] = set()

    def walk(directory: Path) -> Iterable[Path]:
        try:
            real_directory = directory.resolve(strict=True)
            stat = directory.stat()
        except (OSError, RuntimeError) as error:
            warnings.append(f"跳过不可解析技能目录 {directory}: {error}")
            return
        if not is_within(real_directory, refer_root):
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
                    if not is_within(resolved, refer_root):
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
                    yield from walk(child)
            except OSError as error:
                warnings.append(f"跳过不可访问技能路径 {child}: {error}")
                continue

    yield from walk(skills_root)


def normalize_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
        if value and value[0] in {'"', "'"}:
            value = value.replace(value[0] + value[0], value[0])
    return value.strip()


def read_frontmatter(path: Path) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(FRONTMATTER_LIMIT)
    except OSError as error:
        warnings.append(f"frontmatter 读取失败 {path}: {error}")
        return path.parent.name, "", warnings

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
        values[key] = normalize_scalar(raw_value)
        index += 1

    name = values.get("name", "").strip()
    if not name:
        warnings.append(f"frontmatter 缺少 name，使用目录名作为技能名: {path}")
        name = path.parent.name
    elif name == "<name>":
        warnings.append(f"frontmatter 使用模板 name=<name>，回退目录名: {path}")
        name = path.parent.name
    return name, values.get("description", "").strip(), warnings


def classify(path: Path, refer_root: Path) -> tuple[str, str, str]:
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
    elif parts.count("skills") > 1:
        kind = "nested"
    else:
        kind = "standard"
    return source_repo, lifecycle, kind


def compact(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def discover(configure_root: Path) -> tuple[Path, list[SkillRecord], list[str]]:
    _root, refer_root = resolve_root(configure_root)
    by_real_path: dict[Path, Path] = {}
    warnings: list[str] = []
    for skills_root in iter_skills_roots(refer_root, warnings):
        for skill_file in iter_skill_files(skills_root, refer_root, warnings):
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
            source_repo, lifecycle, kind = classify(skill_file, refer_root)
        except (OSError, RuntimeError, ValueError) as error:
            warnings.append(f"跳过无法分类路径 {skill_file}: {error}")
            continue
        name, description, frontmatter_warnings = read_frontmatter(skill_file)
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
    warnings = list(dict.fromkeys(warnings))
    return refer_root, records, warnings


def tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+", value.casefold()) if token]


def match_score(record: SkillRecord, query: str) -> int:
    normalized_query = " ".join(query.casefold().split())
    if not normalized_query:
        return 0
    name = record.name.casefold()
    directory_name = record.directory_name.casefold()
    description = record.description.casefold()
    path = record.path.as_posix().casefold()
    query_tokens = list(dict.fromkeys(tokens(normalized_query)))

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


def lifecycle_rank(record: SkillRecord) -> int:
    return {"active": 0, "in-progress": 1, "deprecated": 2}.get(record.lifecycle, 3)


def kind_rank(record: SkillRecord) -> int:
    return {"standard": 0, "nested": 1, "plugin": 2}.get(record.kind, 3)


def record_payload(record: SkillRecord, score: int) -> dict[str, object]:
    return {
        "name": record.name,
        "directory_name": record.directory_name,
        "description": compact(record.description),
        "path": str(record.path),
        "resolved_path": str(record.resolved_path),
        "source_repo": record.source_repo,
        "lifecycle": record.lifecycle,
        "kind": record.kind,
        "score": score,
    }


def as_tsv(records: list[tuple[SkillRecord, int]]) -> str:
    lines = ["score\tname\tlifecycle\trepo\tpath\tdescription"]
    for record, score in records:
        description = compact(record.description, 220).replace("\t", " ").replace("\n", " ")
        lines.append(
            f"{score}\t{record.name}\t{record.lifecycle}\t{record.source_repo}\t"
            f"{record.path}\t{description}"
        )
    return "\n".join(lines)


def parse_nonnegative(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是整数") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须大于等于 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="发现 refer/git-rep/**/skills 中的 SKILL.md，并支持名称或语义关键词筛选。",
    )
    parser.add_argument("--root", type=Path, default=default_configure_root(), help="configure 仓库根目录")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--query", default="", help="名称、描述和路径的关键词查询")
    selector.add_argument("--name", help="按 frontmatter name 精确筛选")
    selector.add_argument("--path", type=Path, help="精确检查 SKILL.md 或技能目录")
    parser.add_argument("--limit", type=parse_nonnegative, default=20, help="最多返回条数；0 表示全部")
    parser.add_argument("--format", choices=("json", "tsv"), default="json", help="输出格式")
    return parser


def select_records(
    records: list[SkillRecord],
    *,
    query: str,
    name: str | None,
    exact_path: Path | None,
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
        if "skills" not in displayed_parts and "skills" not in resolved.parts:
            raise DiscoveryError(f"路径不在 refer/git-rep/**/skills 下: {candidate}")
        if not is_within(resolved, refer_root):
            raise DiscoveryError(f"路径越出参考根 {refer_root}: {candidate}")
        matches: list[tuple[SkillRecord, int]] = []
        for record in records:
            if record.resolved_path != resolved:
                continue
            classification_path = candidate if is_within(candidate, refer_root) else resolved
            source_repo, lifecycle, kind = classify(classification_path, refer_root)
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
        matches.sort(
            key=lambda item: (
                lifecycle_rank(item[0]),
                kind_rank(item[0]),
                len(item[0].path.parts),
                item[0].path.as_posix(),
            )
        )
        return matches

    scored = [(record, match_score(record, query)) for record in records]
    if query:
        scored = [item for item in scored if item[1] > 0]
    scored.sort(
        key=lambda item: (
            -item[1],
            lifecycle_rank(item[0]),
            kind_rank(item[0]),
            len(item[0].path.parts),
            item[0].name.casefold(),
            item[0].path.as_posix(),
        )
    )
    return scored


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root, refer_root = resolve_root(args.root)
        _refer_root, records, warnings = discover(root)
        selected = select_records(
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
    duplicate_names = sorted(
        name
        for name in {record.name for record in records}
        if sum(1 for record in records if record.name == name) > 1
    )

    if args.format == "tsv":
        print(as_tsv(selected))
        return 0

    payload = {
        "configure_root": str(root),
        "refer_root": str(refer_root),
        "query": args.query,
        "name_filter": args.name,
        "path_filter": str(args.path) if args.path else None,
        "candidate_count": len(records),
        "returned_count": len(selected),
        "duplicate_names": duplicate_names,
        "warnings": warnings,
        "matches": [record_payload(record, score) for record, score in selected],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
