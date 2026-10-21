#!/usr/bin/env python3
"""Offline regression cases invoked by find-refer-skills.test.sh."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("find-refer-skills.py")
SKILL_DIR = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("find_refer_skills", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FindReferSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="conf-refer-test-", dir=SKILL_DIR)
        self.root = Path(self.temporary.name)
        self.refer_root = self.root / "refer" / "git-rep"
        self.refer_root.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_skill(self, relative: str, name: str, description: str, body: str = "") -> Path:
        path = self.refer_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n{body}\n",
            encoding="utf-8",
        )
        return path

    def run_cli_for(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), *args],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired as error:
            self.fail(f"CLI 回归超过 30 秒硬时限: {error}")

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli_for(self.root, *args)

    def test_discovers_standard_plugin_and_nested_skills_roots(self) -> None:
        self.write_skill("repo-a/skills/alpha/SKILL.md", "alpha", "Peer review of papers")
        self.write_skill("repo-b/plugins/demo/skills/beta/SKILL.md", "beta", "Scientific visualization")
        self.write_skill("repo-c/skills/skills/category/gamma/SKILL.md", "gamma", "Data analysis")
        self.write_skill("repo-d/agent_skills/delta/SKILL.md", "delta", "Agent orchestration")
        self.write_skill("repo-a/other/ignored/SKILL.md", "ignored", "Must not be discovered")

        process = self.run_cli("--limit", "0")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual({item["name"] for item in payload["matches"]}, {"alpha", "beta", "gamma", "delta"})
        self.assertEqual(payload["candidate_count"], 4)
        delta = next(item for item in payload["matches"] if item["name"] == "delta")
        self.assertEqual(delta["kind"], "standard")

    def test_query_and_exact_name_selection(self) -> None:
        self.write_skill("repo-a/skills/alpha/SKILL.md", "alpha", "Peer review of scientific papers")
        self.write_skill("repo-b/skills/beta/SKILL.md", "beta", "Scientific visualization and charts")

        query_process = self.run_cli("--query", "paper review")
        self.assertEqual(query_process.returncode, 0, query_process.stderr)
        query_payload = json.loads(query_process.stdout)
        self.assertEqual(query_payload["matches"][0]["name"], "alpha")

        name_process = self.run_cli("--name", "beta")
        self.assertEqual(name_process.returncode, 0, name_process.stderr)
        name_payload = json.loads(name_process.stdout)
        self.assertEqual([item["name"] for item in name_payload["matches"]], ["beta"])

        workspace_alias = self.root / "workspace"
        os.symlink(self.refer_root, workspace_alias)
        external_path = workspace_alias / "repo-a" / "skills" / "alpha" / "SKILL.md"
        external_process = self.run_cli("--path", str(external_path))
        self.assertEqual(external_process.returncode, 0, external_process.stderr)
        external_payload = json.loads(external_process.stdout)
        self.assertEqual(external_payload["matches"][0]["source_repo"], "repo-a")
        self.assertEqual(external_payload["matches"][0]["path"], str(external_path))

    def test_symlinks_stay_inside_refer_root_and_duplicate_real_files(self) -> None:
        target = self.refer_root / "repo-a" / "real" / "alpha"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: linked skill\n---\n# Alpha\n",
            encoding="utf-8",
        )
        skills_root = self.refer_root / "repo-a" / "skills"
        skills_root.mkdir(parents=True)
        os.symlink("../real/alpha", skills_root / "alias-a")
        os.symlink("../real/alpha", skills_root / "alias-b")

        outside = self.root / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text(
            "---\nname: outside\ndescription: forbidden\n---\n",
            encoding="utf-8",
        )
        os.symlink("../../../../outside", skills_root / "outside")
        os.symlink("loop", skills_root / "loop")
        os.symlink("../missing", skills_root / "broken")

        process = self.run_cli("--limit", "0")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual([item["name"] for item in payload["matches"]], ["alpha"])
        self.assertEqual(payload["candidate_count"], 1)
        self.assertTrue(any("越出参考根" in warning for warning in payload["warnings"]))
        self.assertTrue(any("不可解析" in warning or "断链" in warning for warning in payload["warnings"]))

        alias_process = self.run_cli("--path", str(skills_root / "alias-b" / "SKILL.md"))
        self.assertEqual(alias_process.returncode, 0, alias_process.stderr)
        alias_payload = json.loads(alias_process.stdout)
        self.assertIn("/skills/alias-b/", alias_payload["matches"][0]["path"])

        loop_process = self.run_cli("--path", str(skills_root / "loop" / "SKILL.md"))
        self.assertEqual(loop_process.returncode, 2)
        self.assertIn("不可解析", loop_process.stderr)

        tsv_process = self.run_cli("--limit", "0", "--format", "tsv")
        self.assertEqual(tsv_process.returncode, 0, tsv_process.stderr)
        self.assertIn("alpha", tsv_process.stdout)
        self.assertIn("warning:", tsv_process.stderr)
        self.assertIn("越出参考根", tsv_process.stderr)

    def test_cross_repo_symlink_reports_resolved_source(self) -> None:
        target = self.refer_root / "repo-b" / "real" / "cross"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text(
            "---\nname: cross\ndescription: cross-repository link\n---\n# Cross\n",
            encoding="utf-8",
        )
        skills_root = self.refer_root / "repo-a" / "skills"
        skills_root.mkdir(parents=True)
        os.symlink("../../repo-b/real/cross", skills_root / "cross")

        process = self.run_cli("--name", "cross")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["matches"][0]["source_repo"], "repo-b")
        self.assertIn("/repo-a/skills/cross/SKILL.md", payload["matches"][0]["path"])

    def test_path_filter_rejects_outside_root_and_reports_duplicate_names(self) -> None:
        self.write_skill("repo-a/plugins/demo/skills/plan/SKILL.md", "plan", "Plugin planner")
        first = self.write_skill("repo-b/skills/plan/SKILL.md", "plan", "Canonical planner")
        outside = self.root / "outside" / "SKILL.md"
        outside.parent.mkdir(parents=True)
        outside.write_text("---\nname: outside\ndescription: forbidden\n---\n", encoding="utf-8")

        exact_process = self.run_cli("--path", str(first))
        self.assertEqual(exact_process.returncode, 0, exact_process.stderr)
        exact_payload = json.loads(exact_process.stdout)
        self.assertEqual(exact_payload["matches"][0]["name"], "plan")
        self.assertIn("plan", exact_payload["duplicate_names"])

        name_process = self.run_cli("--name", "plan")
        self.assertEqual(name_process.returncode, 0, name_process.stderr)
        name_payload = json.loads(name_process.stdout)
        self.assertEqual(name_payload["matches"][0]["kind"], "standard")

        outside_process = self.run_cli("--path", str(outside))
        self.assertEqual(outside_process.returncode, 2)
        self.assertIn("越出参考根", outside_process.stderr)

    def test_missing_frontmatter_and_block_description_are_tolerated(self) -> None:
        missing = self.refer_root / "repo-a" / "skills" / "plain" / "SKILL.md"
        missing.parent.mkdir(parents=True)
        missing.write_text("# Plain skill\n", encoding="utf-8")
        blocked = self.refer_root / "repo-b" / "skills" / "blocked" / "SKILL.md"
        blocked.parent.mkdir(parents=True)
        blocked.write_text(
            "---\nname: blocked\ndescription: |\n  First line\n  second line\n---\n# Blocked\n",
            encoding="utf-8",
        )

        process = self.run_cli("--limit", "0")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        by_name = {item["name"]: item for item in payload["matches"]}
        self.assertIn("plain", by_name)
        self.assertEqual(by_name["blocked"]["description"], "First line second line")
        self.assertTrue(any("缺少 frontmatter" in warning for warning in payload["warnings"]))

    def test_quoted_values_and_tsv_fields_are_escaped(self) -> None:
        quoted = self.refer_root / "repo-a" / "skills" / "quoted" / "SKILL.md"
        quoted.parent.mkdir(parents=True)
        quoted.write_text(
            "---\nname: 'tab\tname' # comment\ndescription: 'It''s a quoted # skill' # comment\n---\n# Quoted\n",
            encoding="utf-8",
        )
        commented = self.refer_root / "repo-b" / "skills" / "commented" / "SKILL.md"
        commented.parent.mkdir(parents=True)
        commented.write_text(
            "---\nname: commented # canonical\ndescription: \"line\x1b]0;title\x07\" # terminal control\n---\n",
            encoding="utf-8",
        )

        json_process = self.run_cli("--limit", "0")
        self.assertEqual(json_process.returncode, 0, json_process.stderr)
        payload = json.loads(json_process.stdout)
        match = next(item for item in payload["matches"] if item["directory_name"] == "quoted")
        self.assertEqual(match["name"], "tab name")
        self.assertEqual(match["description"], "It's a quoted # skill")
        commented_match = next(item for item in payload["matches"] if item["directory_name"] == "commented")
        self.assertEqual(commented_match["name"], "commented")
        self.assertNotIn("\x1b", commented_match["description"])
        self.assertNotIn("\x07", commented_match["description"])

        tsv_process = self.run_cli("--limit", "0", "--format", "tsv")
        self.assertEqual(tsv_process.returncode, 0, tsv_process.stderr)
        for line in tsv_process.stdout.splitlines():
            self.assertEqual(len(line.split("\t")), 6, line)
        self.assertNotIn("\x1b", tsv_process.stdout)
        self.assertNotIn("\x07", tsv_process.stdout)

        control_path = self.refer_root / "repo-c" / "skills" / "bad\x9bpath" / "SKILL.md"
        control_path.parent.mkdir(parents=True)
        control_path.write_text("---\nname: control-path\ndescription: path test\n---\n", encoding="utf-8")
        json_control = self.run_cli("--name", "control-path")
        self.assertEqual(json_control.returncode, 0, json_control.stderr)
        self.assertNotIn("\x9b", json_control.stdout)

    def test_reader_rejects_outside_target_and_empty_root_warns(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        outside_skill = outside / "SKILL.md"
        outside_skill.write_text("---\nname: secret\ndescription: SECRET\n---\n", encoding="utf-8")
        skills_root = self.refer_root / "repo-a" / "skills"
        skills_root.mkdir(parents=True)
        link = skills_root / "outside"
        link.mkdir()
        os.symlink(outside_skill, link / "SKILL.md")

        name, description, warnings = MODULE._read_frontmatter(link / "SKILL.md", self.refer_root)
        self.assertEqual(name, "outside")
        self.assertEqual(description, "")
        self.assertTrue(any("越界" in warning for warning in warnings))

        empty_root = self.root / "empty-root"
        (empty_root / "refer" / "git-rep").mkdir(parents=True)
        process = self.run_cli_for(empty_root, "--limit", "0")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["candidate_count"], 0)
        self.assertTrue(any("未发现任何名称以 skills" in warning for warning in payload["warnings"]))

    def test_root_symlink_loop_returns_controlled_error(self) -> None:
        loop_root = self.root / "loop-root"
        (loop_root / "refer").mkdir(parents=True)
        os.symlink("git-rep", loop_root / "refer" / "git-rep")

        process = self.run_cli_for(loop_root, "--limit", "0")
        self.assertEqual(process.returncode, 2)
        self.assertIn("不可解析", process.stderr)
        self.assertNotIn("Traceback", process.stderr)


if __name__ == "__main__":
    unittest.main()
