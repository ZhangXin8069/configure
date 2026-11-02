#!/usr/bin/env python3
"""Regression tests for the paired agent configuration benchmark."""

from __future__ import annotations

import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("agent-config-benchmark.py")
SPEC = importlib.util.spec_from_file_location("agent_config_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class AgentConfigBenchmarkTest(unittest.TestCase):
    def test_sample_selection_is_stable_and_prefix_preserving(self) -> None:
        tasks = [{"task_id": f"HumanEval/{index}"} for index in range(20)]
        first = benchmark._select_tasks(tasks, 5, "stable-seed", [])
        second = benchmark._select_tasks(tasks, 9, "stable-seed", [])
        self.assertEqual(first, second[:5])

    def test_humaneval_loader_and_evaluator_use_hidden_tests(self) -> None:
        task = {
            "task_id": "HumanEval/unit",
            "entry_point": "add",
            "prompt": "def add(left, right):\n    \"\"\"Return the sum.\"\"\"\n",
            "canonical_solution": "    return left + right\n",
            "test": "def check(candidate):\n    assert candidate(2, 3) == 5\n",
        }
        with tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
            root = Path(temporary)
            dataset = root / "HumanEval.jsonl.gz"
            with gzip.open(dataset, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps(task) + "\n")
            loaded = benchmark._load_humaneval(dataset)
            workspace = root / "workspace"
            workspace.mkdir()
            solution = workspace / "solution.py"
            solution.write_text(task["prompt"] + task["canonical_solution"], encoding="utf-8")
            self.assertTrue(benchmark._evaluate_solution(loaded[0], solution, workspace, 2)["passed"])
            solution.write_text(task["prompt"] + "    return 0\n", encoding="utf-8")
            self.assertFalse(benchmark._evaluate_solution(loaded[0], solution, workspace, 2)["passed"])

    def test_summary_reports_aggregate_ratios(self) -> None:
        def row(task_id: str, arm: str, correct: bool, tokens: int, wall: float) -> dict:
            return {
                "task_id": task_id,
                "arm": arm,
                "correct": correct,
                "wall_seconds": wall,
                "dispatch_timed_out": False,
                "dispatch_rc": 0,
                "evaluation": {"timed_out": False},
                "out_of_scope_file_changes": [],
                "agent_usage": {
                    "total_tokens": tokens,
                    "uncached_input_tokens": tokens // 2,
                    "output_tokens": tokens // 10,
                    "item_types": {},
                },
            }

        rows = [
            row("HumanEval/0", "native", True, 100, 10),
            row("HumanEval/0", "library", True, 300, 20),
            row("HumanEval/1", "native", True, 200, 20),
            row("HumanEval/1", "library", False, 500, 40),
        ]
        summary = benchmark._summarize(rows, "test-seed")
        self.assertEqual(summary["arms"]["native"]["pass_rate"], 1.0)
        self.assertEqual(summary["arms"]["library"]["pass_rate"], 0.5)
        self.assertEqual(summary["paired"]["total_tokens_ratio_library_over_native_aggregate"], 2.6667)
        self.assertEqual(summary["paired"]["wall_seconds_ratio_library_over_native_aggregate"], 2.0)

    def test_dataset_hash_guard(self) -> None:
        with tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
            dataset = Path(temporary) / "dataset.bin"
            dataset.write_bytes(b"known")
            expected = benchmark._sha256(dataset)
            self.assertEqual(benchmark._ensure_dataset(dataset, False, expected), expected)
            with self.assertRaises(ValueError):
                benchmark._ensure_dataset(dataset, False, "0" * 64)


if __name__ == "__main__":
    unittest.main()
