#!/usr/bin/env python3
"""Paired HumanEval benchmark for configure and minimal agent prompts."""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import random
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / "bin" / "agent-dispatch.sh"
DEFAULT_DATASET = ROOT / "data" / "cache" / "agent-config-benchmark" / "20261102" / "HumanEval.jsonl.gz"
DATASET_COMMIT = "b9453e8f1865df0a0057a1383767caa400acfbcf"
DATASET_URL = f"https://raw.githubusercontent.com/openai/human-eval/{DATASET_COMMIT}/data/HumanEval.jsonl.gz"
DATASET_SHA256 = "b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef"
DATASET_LICENSE = "MIT"


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value)


def _inside_root(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"path escapes repository root: {resolved}")
    return resolved


def _load_humaneval(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                tasks.append(json.loads(line))
    required = {"task_id", "entry_point", "prompt", "canonical_solution", "test"}
    for task in tasks:
        missing = required.difference(task)
        if missing:
            raise ValueError(f"dataset task missing fields: {sorted(missing)}")
    return tasks


def _ensure_dataset(path: Path, download: bool, expected_sha256: str) -> str:
    if not path.is_file():
        if not download:
            raise FileNotFoundError(f"dataset not found; rerun with --download-dataset: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".download")
        try:
            with urllib.request.urlopen(DATASET_URL, timeout=30) as response, temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            actual = _sha256(temporary)
            if actual != expected_sha256:
                raise ValueError(f"downloaded dataset hash mismatch: {actual}")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    actual = _sha256(path)
    if actual != expected_sha256:
        raise ValueError(f"dataset hash mismatch: expected {expected_sha256}, got {actual}")
    return actual


def _select_tasks(
    tasks: list[dict[str, Any]], sample_size: int, seed: str, task_ids: list[str]
) -> list[dict[str, Any]]:
    by_id = {str(task["task_id"]): task for task in tasks}
    if task_ids:
        missing = [task_id for task_id in task_ids if task_id not in by_id]
        if missing:
            raise ValueError(f"unknown task ids: {missing}")
        return [by_id[task_id] for task_id in task_ids]
    if sample_size < 1 or sample_size > len(tasks):
        raise ValueError(f"sample size must be between 1 and {len(tasks)}")
    ordered = sorted(tasks, key=lambda task: hashlib.sha256(f"{seed}:{task['task_id']}".encode()).hexdigest())
    return ordered[:sample_size]


def _task_prompt(task: dict[str, Any]) -> str:
    return f"""Complete the HumanEval task in `solution.py` in the current directory.

The file already contains the official prompt. Keep the public function name and signature unchanged, replace the empty body with a correct implementation, and use only the Python standard library. You may run your own tests. Do not modify files outside the current directory. The final deliverable is the executable `solution.py` file.

Official prompt:

```python
{task['prompt']}```
"""


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_progress(path: Path, phase: str, **details: Any) -> None:
    _write_json(
        path,
        {
            "updated_at": _utc_now(),
            "phase": phase,
            **details,
        },
    )


def _run_with_group_timeout(
    command: list[str],
    cwd: Path,
    timeout_seconds: float,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str],
) -> tuple[int, bool, float]:
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            start_new_session=True,
        )
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            return_code = 124
    return return_code, timed_out, round(time.monotonic() - started, 3)


def _read_last_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _parse_agent_log(path: Path | None) -> dict[str, Any]:
    usage = Counter()
    item_types = Counter()
    file_change_paths: list[str] = []
    turn_completions = 0
    if not path or not path.is_file():
        return {
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_output_tokens": None,
            "total_tokens": None,
            "uncached_input_tokens": None,
            "turn_completions": 0,
            "item_types": {},
            "file_change_paths": [],
        }
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.completed":
            turn_completions += 1
            event_usage = event.get("usage")
            if isinstance(event_usage, dict):
                for key in (
                    "input_tokens",
                    "cached_input_tokens",
                    "cache_write_input_tokens",
                    "output_tokens",
                    "reasoning_output_tokens",
                ):
                    value = event_usage.get(key)
                    if isinstance(value, int):
                        usage[key] += value
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict):
            item_type = item.get("type")
            if isinstance(item_type, str):
                item_types[item_type] += 1
            if item_type == "file_change" and isinstance(item.get("changes"), list):
                for change in item["changes"]:
                    if isinstance(change, dict) and isinstance(change.get("path"), str):
                        file_change_paths.append(change["path"])
    input_tokens = usage["input_tokens"] if turn_completions else None
    output_tokens = usage["output_tokens"] if turn_completions else None
    cached_input_tokens = usage["cached_input_tokens"] if turn_completions else None
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_write_input_tokens": usage["cache_write_input_tokens"] if turn_completions else None,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": usage["reasoning_output_tokens"] if turn_completions else None,
        "total_tokens": input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None,
        "uncached_input_tokens": input_tokens - cached_input_tokens
        if input_tokens is not None and cached_input_tokens is not None
        else None,
        "turn_completions": turn_completions,
        "item_types": dict(sorted(item_types.items())),
        "file_change_paths": sorted(set(file_change_paths)),
    }


def _evaluate_solution(task: dict[str, Any], solution_path: Path, workspace: Path, timeout: float) -> dict[str, Any]:
    if not solution_path.is_file():
        return {"passed": False, "exit_code": None, "timed_out": False, "output_tail": "solution.py is missing"}
    evaluator_path = workspace / ".humaneval-eval.py"
    evaluator_path.write_text(
        solution_path.read_text(encoding="utf-8", errors="replace")
        + "\n\n"
        + str(task["test"])
        + f"\n\ncheck({task['entry_point']})\n",
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(evaluator_path)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        return {
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "timed_out": False,
            "output_tail": output[-2000:],
        }
    except subprocess.TimeoutExpired as error:
        output = ((error.stdout or "") + (error.stderr or "")).strip() if isinstance(error.stdout, str) else ""
        return {"passed": False, "exit_code": 124, "timed_out": True, "output_tail": output[-2000:]}


def _validate_oracle(tasks: Iterable[dict[str, Any]], output_dir: Path, timeout: float) -> dict[str, Any]:
    oracle_dir = output_dir / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for task in tasks:
        result_path = oracle_dir / f"{_safe_slug(str(task['task_id']))}.json"
        if result_path.is_file():
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            results[str(task["task_id"])] = existing
            print(f"oracle {task['task_id']}: {'PASS' if existing['passed'] else 'FAIL'} (cached)", flush=True)
            continue
        attempt = 1
        while True:
            workspace = oracle_dir / (
                _safe_slug(str(task["task_id"]))
                if attempt == 1
                else f"{_safe_slug(str(task['task_id']))}--{attempt}"
            )
            try:
                workspace.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                attempt += 1
        solution_path = workspace / "solution.py"
        solution_path.write_text(str(task["prompt"]) + str(task["canonical_solution"]), encoding="utf-8")
        result = _evaluate_solution(task, solution_path, workspace, timeout)
        results[str(task["task_id"])] = result
        _write_json(result_path, result)
        print(f"oracle {task['task_id']}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    failed = [task_id for task_id, result in results.items() if not result["passed"]]
    if failed:
        raise RuntimeError(f"oracle validation failed: {failed}")
    return results


def _prepare_workspace(output_dir: Path, task: dict[str, Any], arm: str) -> Path:
    run_root = output_dir / "workspaces"
    run_root.mkdir(parents=True, exist_ok=True)
    base_name = f"{_safe_slug(str(task['task_id']))}--{arm}"
    attempt = 1
    while True:
        workspace = run_root / (base_name if attempt == 1 else f"{base_name}--{attempt}")
        try:
            workspace.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            attempt += 1
    subprocess.run(["git", "init", "-q", str(workspace)], check=True, cwd=ROOT)
    (workspace / "solution.py").write_text(str(task["prompt"]), encoding="utf-8")
    (workspace / "TASK.md").write_text(_task_prompt(task), encoding="utf-8")
    return workspace


def _run_arm(
    task: dict[str, Any],
    arm: str,
    output_dir: Path,
    timeout_seconds: float,
    eval_timeout: float,
    provider: str,
    model: str,
    strength: str,
) -> dict[str, Any]:
    workspace = _prepare_workspace(output_dir, task, arm)
    started_at = _utc_now()
    dispatch_path = output_dir / "results" / f"{workspace.name}.dispatch.json"
    stdout_path = output_dir / "results" / f"{workspace.name}.stdout.jsonl"
    stderr_path = output_dir / "results" / f"{workspace.name}.stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    task_text = _task_prompt(task)
    command = [
        "bash",
        str(DISPATCH),
        "--task",
        task_text,
        "--cwd",
        str(workspace),
        "--agent",
        "co",
        "--provider",
        provider,
        "--model",
        model,
        "--strength",
        strength,
        "--timeout",
        f"{int(timeout_seconds)}s",
        "--json",
    ]
    if arm == "library":
        command.append("--full")
    env = os.environ.copy()
    env["AGENT_MODEL_DISCOVERY"] = "0"
    env["AGENT_AUTO_RESUME"] = "0"
    env["NO_COLOR"] = "1"
    dispatch_rc, dispatch_timed_out, wall_seconds = _run_with_group_timeout(
        command,
        ROOT,
        timeout_seconds + 30,
        stdout_path,
        stderr_path,
        env,
    )
    dispatch_payload = _read_last_json(stdout_path)
    effective_timed_out = dispatch_timed_out or bool(
        dispatch_payload.get("timed_out") if isinstance(dispatch_payload, dict) else False
    )
    log_file_value = dispatch_payload.get("log_file") if isinstance(dispatch_payload, dict) else None
    log_file = Path(log_file_value) if isinstance(log_file_value, str) and log_file_value else None
    usage = _parse_agent_log(log_file)
    workspace_resolved = workspace.resolve()
    out_of_scope_paths: list[str] = []
    for path in usage["file_change_paths"]:
        reported = Path(path)
        resolved = reported.resolve() if reported.is_absolute() else (workspace_resolved / reported).resolve()
        if not resolved.is_relative_to(workspace_resolved):
            out_of_scope_paths.append(path)
    evaluation = _evaluate_solution(task, workspace / "solution.py", workspace, eval_timeout)
    result = {
        "schema_version": "agent-config-benchmark/v1",
        "task_id": task["task_id"],
        "entry_point": task["entry_point"],
        "arm": arm,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "workspace": str(workspace),
        "dispatch_stdout": str(stdout_path),
        "dispatch_stderr": str(stderr_path),
        "dispatch_rc": dispatch_rc,
        "dispatch_timed_out": effective_timed_out,
        "dispatch_ok": bool(dispatch_payload.get("ok")) if isinstance(dispatch_payload, dict) else False,
        "run_id": dispatch_payload.get("run_id") if isinstance(dispatch_payload, dict) else None,
        "agent_log": str(log_file) if log_file else None,
        "agent_usage": usage,
        "out_of_scope_file_changes": out_of_scope_paths,
        "wall_seconds": wall_seconds,
        "correct": bool(evaluation["passed"]),
        "evaluation": evaluation,
        "solution_sha256": _sha256(workspace / "solution.py") if (workspace / "solution.py").is_file() else None,
    }
    _write_json(dispatch_path, result)
    canonical_result = output_dir / "results" / f"{_safe_slug(str(task['task_id']))}--{arm}.result.json"
    _write_json(canonical_result, result)
    return result


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def _wilson_interval(passes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    p = passes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def _mcnemar_exact(left_only: int, right_only: int) -> float | None:
    discordant = left_only + right_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(left_only, right_only) + 1)) / (2**discordant)
    return round(min(1.0, 2 * tail), 6)


def _bootstrap_mean_difference(values: list[float], seed: str, rounds: int = 20000) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(f"{seed}:bootstrap")
    means = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds)]
    means.sort()
    return [round(means[int(0.025 * rounds)], 3), round(means[int(0.975 * rounds) - 1], 3)]


def _summarize(results: list[dict[str, Any]], seed: str) -> dict[str, Any]:
    manifest = sorted({(str(item["task_id"]), str(item["arm"])) for item in results})
    task_ids = sorted({task_id for task_id, _arm in manifest})
    summary: dict[str, Any] = {"arms": {}, "paired": {"task_count": len(task_ids)}}
    for arm in ("native", "library"):
        arm_results = [item for item in results if item["arm"] == arm and item["task_id"] in task_ids]
        passed = sum(bool(item["correct"]) for item in arm_results)
        total_tokens = [
            item["agent_usage"]["total_tokens"]
            for item in arm_results
            if item["agent_usage"]["total_tokens"] is not None
        ]
        uncached = [
            item["agent_usage"]["uncached_input_tokens"]
            for item in arm_results
            if item["agent_usage"]["uncached_input_tokens"] is not None
        ]
        output_tokens = [item["agent_usage"]["output_tokens"] for item in arm_results if item["agent_usage"]["output_tokens"] is not None]
        wall = [float(item["wall_seconds"]) for item in arm_results]
        command_calls = [item["agent_usage"]["item_types"].get("command_execution", 0) for item in arm_results]
        file_changes = [item["agent_usage"]["item_types"].get("file_change", 0) for item in arm_results]
        timeout_count = sum(
            bool(item["dispatch_timed_out"])
            or bool(item["evaluation"]["timed_out"])
            or item.get("dispatch_rc") == 124
            for item in arm_results
        )
        summary["arms"][arm] = {
            "n": len(arm_results),
            "passed": passed,
            "pass_rate": round(passed / len(arm_results), 4) if arm_results else None,
            "pass_rate_wilson_95": _wilson_interval(passed, len(arm_results)),
            "timeout_count": timeout_count,
            "usage_measured_n": len(total_tokens),
            "total_tokens_sum": sum(total_tokens) if total_tokens else None,
            "total_tokens_mean": _mean([float(x) for x in total_tokens]),
            "total_tokens_median": _median([float(x) for x in total_tokens]),
            "uncached_input_tokens_mean": _mean([float(x) for x in uncached]),
            "output_tokens_mean": _mean([float(x) for x in output_tokens]),
            "wall_seconds_mean": _mean(wall),
            "wall_seconds_median": _median(wall),
            "command_calls_mean": _mean([float(x) for x in command_calls]),
            "file_changes_mean": _mean([float(x) for x in file_changes]),
            "out_of_scope_file_change_count": sum(
                len(item.get("out_of_scope_file_changes", [])) for item in arm_results
            ),
            "correct_per_100k_tokens": round(passed / sum(total_tokens) * 100000, 3)
            if total_tokens and sum(total_tokens) > 0
            else None,
            "correct_per_minute": round(passed / (sum(wall) / 60), 3) if sum(wall) > 0 else None,
        }

    by_task_arm = {(str(item["task_id"]), str(item["arm"])): item for item in results}
    paired_tasks = [
        task_id for task_id in task_ids if (task_id, "native") in by_task_arm and (task_id, "library") in by_task_arm
    ]
    left_only = sum(
        not by_task_arm[(task_id, "native")]["correct"] and by_task_arm[(task_id, "library")]["correct"]
        for task_id in paired_tasks
    )
    right_only = sum(
        by_task_arm[(task_id, "native")]["correct"] and not by_task_arm[(task_id, "library")]["correct"]
        for task_id in paired_tasks
    )
    both = sum(
        by_task_arm[(task_id, "native")]["correct"] and by_task_arm[(task_id, "library")]["correct"]
        for task_id in paired_tasks
    )
    token_differences = [
        by_task_arm[(task_id, "library")]["agent_usage"]["total_tokens"]
        - by_task_arm[(task_id, "native")]["agent_usage"]["total_tokens"]
        for task_id in paired_tasks
        if by_task_arm[(task_id, "library")]["agent_usage"]["total_tokens"] is not None
        and by_task_arm[(task_id, "native")]["agent_usage"]["total_tokens"] is not None
    ]
    time_differences = [
        by_task_arm[(task_id, "library")]["wall_seconds"] - by_task_arm[(task_id, "native")]["wall_seconds"]
        for task_id in paired_tasks
    ]
    correctness_differences = [
        float(by_task_arm[(task_id, "library")]["correct"]) - float(by_task_arm[(task_id, "native")]["correct"])
        for task_id in paired_tasks
    ]
    token_ratios = [
        by_task_arm[(task_id, "library")]["agent_usage"]["total_tokens"]
        / by_task_arm[(task_id, "native")]["agent_usage"]["total_tokens"]
        for task_id in paired_tasks
        if by_task_arm[(task_id, "library")]["agent_usage"]["total_tokens"] is not None
        and by_task_arm[(task_id, "native")]["agent_usage"]["total_tokens"]
    ]
    time_ratios = [
        by_task_arm[(task_id, "library")]["wall_seconds"] / by_task_arm[(task_id, "native")]["wall_seconds"]
        for task_id in paired_tasks
        if by_task_arm[(task_id, "native")]["wall_seconds"] > 0
    ]
    summary["paired"] = {
        "task_count": len(paired_tasks),
        "both_correct": both,
        "library_only_correct": left_only,
        "native_only_correct": right_only,
        "pass_rate_difference_library_minus_native": round(
            statistics.fmean(correctness_differences), 4
        )
        if correctness_differences
        else None,
        "pass_rate_difference_bootstrap_95": _bootstrap_mean_difference(correctness_differences, seed),
        "mcnemar_exact_two_sided_p": _mcnemar_exact(left_only, right_only),
        "total_tokens_difference_mean": _mean([float(x) for x in token_differences]),
        "total_tokens_difference_bootstrap_95": _bootstrap_mean_difference(
            [float(x) for x in token_differences], seed
        ),
        "total_tokens_ratio_library_over_native_mean": _mean([float(x) for x in token_ratios]),
        "total_tokens_ratio_library_over_native_median": _median([float(x) for x in token_ratios]),
        "wall_seconds_difference_mean": _mean(time_differences),
        "wall_seconds_difference_bootstrap_95": _bootstrap_mean_difference(time_differences, seed),
        "wall_seconds_ratio_library_over_native_mean": _mean([float(x) for x in time_ratios]),
        "wall_seconds_ratio_library_over_native_median": _median([float(x) for x in time_ratios]),
        "total_tokens_ratio_library_over_native_aggregate": round(
            summary["arms"]["library"]["total_tokens_sum"] / summary["arms"]["native"]["total_tokens_sum"], 4
        ),
        "wall_seconds_ratio_library_over_native_aggregate": round(
            sum(item["wall_seconds"] for item in results if item["arm"] == "library" and item["task_id"] in task_ids)
            / sum(item["wall_seconds"] for item in results if item["arm"] == "native" and item["task_id"] in task_ids),
            4,
        ),
        "uncached_input_tokens_ratio_library_over_native_aggregate": round(
            sum(
                item["agent_usage"]["uncached_input_tokens"]
                for item in results
                if item["arm"] == "library" and item["task_id"] in task_ids
            )
            / sum(
                item["agent_usage"]["uncached_input_tokens"]
                for item in results
                if item["arm"] == "native" and item["task_id"] in task_ids
            ),
            4,
        ),
        "output_tokens_ratio_library_over_native_aggregate": round(
            sum(
                item["agent_usage"]["output_tokens"]
                for item in results
                if item["arm"] == "library" and item["task_id"] in task_ids
            )
            / sum(
                item["agent_usage"]["output_tokens"]
                for item in results
                if item["arm"] == "native" and item["task_id"] in task_ids
            ),
            4,
        ),
    }
    return summary


def _write_markdown_summary(path: Path, summary: dict[str, Any], metadata: dict[str, Any]) -> None:
    native = summary["arms"]["native"]
    library = summary["arms"]["library"]
    paired = summary["paired"]
    lines = [
        "# Agent config HumanEval benchmark",
        "",
        f"- dataset_sha256: `{metadata['dataset_sha256']}`",
        f"- dataset_commit: `{metadata['dataset_commit']}` ({metadata['dataset_license']})",
        f"- sample_seed: `{metadata['seed']}`",
        f"- paired_tasks: `{paired['task_count']}`",
        f"- model: `{metadata['model']}` via `{metadata['provider']}`, strength `{metadata['strength']}`",
        "",
        "| arm | pass@1 | Wilson 95% | token n | mean total tokens | mean wall s | timeouts | commands/run | correct/100k tokens | correct/min |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, arm in (("native", native), ("library", library)):
        lines.append(
            f"| {name} | {arm['passed']}/{arm['n']} ({arm['pass_rate']:.1%}) | "
            f"{arm['pass_rate_wilson_95']} | {arm['usage_measured_n']}/{arm['n']} | {arm['total_tokens_mean']} | "
            f"{arm['wall_seconds_mean']} | {arm['timeout_count']} | {arm['command_calls_mean']} | "
            f"{arm['correct_per_100k_tokens']} | {arm['correct_per_minute']} |"
        )
    lines.extend(
        [
            "",
            "## Paired comparison",
            "",
            f"- pass-rate difference (library - native): `{paired['pass_rate_difference_library_minus_native']}`; "
            f"bootstrap 95% `{paired['pass_rate_difference_bootstrap_95']}`; McNemar exact p=`{paired['mcnemar_exact_two_sided_p']}`.",
            f"- mean total-token difference: `{paired['total_tokens_difference_mean']}`; "
            f"bootstrap 95% `{paired['total_tokens_difference_bootstrap_95']}`; "
            f"mean ratio library/native `{paired['total_tokens_ratio_library_over_native_mean']}`.",
            f"- mean wall-time difference: `{paired['wall_seconds_difference_mean']}` s; "
            f"bootstrap 95% `{paired['wall_seconds_difference_bootstrap_95']}`; "
            f"mean ratio library/native `{paired['wall_seconds_ratio_library_over_native_mean']}`.",
            f"- aggregate ratios library/native: total tokens `{paired['total_tokens_ratio_library_over_native_aggregate']}x`, "
            f"uncached input `{paired['uncached_input_tokens_ratio_library_over_native_aggregate']}x`, "
            f"output `{paired['output_tokens_ratio_library_over_native_aggregate']}x`, "
            f"wall time `{paired['wall_seconds_ratio_library_over_native_aggregate']}x`.",
            "",
            "Scope: HumanEval algorithmic code generation with one fresh agent thread per task. "
            "The native arm uses agent-dispatch's minimal prompt; the library arm uses the full configure prompt and skills. "
            "Both use the same launcher, provider, model, strength, workspace layout, timeout, and hidden tests.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--download-dataset", action="store_true")
    parser.add_argument("--expected-dataset-sha256", default=DATASET_SHA256)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--seed", default="configure-agent-benchmark-v1")
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--eval-timeout-seconds", type=float, default=5)
    parser.add_argument("--provider", default="go")
    parser.add_argument("--model", default="deepseek-v4.1-flash")
    parser.add_argument("--strength", default="max")
    parser.add_argument("--resume", action="store_true", help="reuse completed result files and run missing pairs")
    parser.add_argument("--progress-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = _inside_root(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    prior_manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(prior_manifest, dict):
            raise ValueError(f"invalid benchmark manifest: {manifest_path}")
    result_files = list((output_dir / "results").glob("*.result.json")) if (output_dir / "results").is_dir() else []
    if args.resume and result_files and prior_manifest is None:
        raise ValueError("cannot resume existing results without manifest.json")
    progress_file = _inside_root(args.progress_file) if args.progress_file else output_dir / "progress.json"
    _write_progress(progress_file, "starting")
    dataset = _inside_root(args.dataset)
    dataset_sha256 = _ensure_dataset(dataset, args.download_dataset, args.expected_dataset_sha256)
    tasks = _select_tasks(_load_humaneval(dataset), args.sample_size, args.seed, args.task_id)
    metadata = {
        "schema_version": "agent-config-benchmark/v1",
        "created_at": prior_manifest.get("created_at", _utc_now()) if prior_manifest else _utc_now(),
        "updated_at": _utc_now(),
        "dataset": str(dataset),
        "dataset_sha256": dataset_sha256,
        "dataset_commit": DATASET_COMMIT,
        "dataset_url": DATASET_URL,
        "dataset_license": DATASET_LICENSE,
        "seed": args.seed,
        "task_ids": [task["task_id"] for task in tasks],
        "provider": args.provider,
        "model": args.model,
        "strength": args.strength,
        "timeout_seconds": args.timeout_seconds,
        "eval_timeout_seconds": args.eval_timeout_seconds,
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip(),
    }
    if args.resume and prior_manifest:
        keys = (
            "dataset_sha256",
            "seed",
            "task_ids",
            "provider",
            "model",
            "strength",
            "timeout_seconds",
            "eval_timeout_seconds",
        )
        mismatches = [key for key in keys if prior_manifest.get(key) != metadata.get(key)]
        if mismatches:
            raise ValueError(f"resume configuration mismatch: {mismatches}")
    _write_json(manifest_path, metadata)
    _write_progress(progress_file, "validating-oracle", task_count=len(tasks))
    _validate_oracle(tasks, output_dir, args.eval_timeout_seconds)
    results: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        arms = ("native", "library") if index % 2 == 0 else ("library", "native")
        for arm in arms:
            result_path = output_dir / "results" / f"{_safe_slug(str(task['task_id']))}--{arm}.result.json"
            if args.resume and result_path.is_file():
                results.append(json.loads(result_path.read_text(encoding="utf-8")))
                _write_progress(
                    progress_file,
                    "running",
                    task_id=task["task_id"],
                    arm=arm,
                    task_index=index + 1,
                    task_count=len(tasks),
                    completed_pairs=len(results),
                )
                print(f"skip {task['task_id']} {arm}: existing result", flush=True)
                continue
            _write_progress(
                progress_file,
                "running",
                task_id=task["task_id"],
                arm=arm,
                task_index=index + 1,
                task_count=len(tasks),
                completed_pairs=len(results),
            )
            print(f"run {task['task_id']} {arm}", flush=True)
            result = _run_arm(
                task,
                arm,
                output_dir,
                args.timeout_seconds,
                args.eval_timeout_seconds,
                args.provider,
                args.model,
                args.strength,
            )
            results.append(result)
            if result["out_of_scope_file_changes"]:
                raise RuntimeError(
                    f"agent wrote outside task workspace for {task['task_id']} {arm}: "
                    f"{result['out_of_scope_file_changes']}"
                )
            _write_progress(
                progress_file,
                "running",
                task_id=task["task_id"],
                arm=arm,
                task_index=index + 1,
                task_count=len(tasks),
                completed_pairs=len(results),
            )
            usage = result["agent_usage"]
            print(
                f"done {task['task_id']} {arm}: correct={result['correct']} "
                f"tokens={usage['total_tokens']} wall={result['wall_seconds']}s",
                flush=True,
            )
    summary = _summarize(results, args.seed)
    _write_json(output_dir / "summary.json", summary)
    _write_markdown_summary(output_dir / "summary.md", summary, metadata)
    _write_progress(progress_file, "finished", completed_pairs=len(results), task_count=len(tasks))
    print(output_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
