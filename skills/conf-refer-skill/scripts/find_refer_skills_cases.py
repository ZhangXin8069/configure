#!/usr/bin/env python3
"""Offline regression cases invoked by find-refer-skills.test.sh."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("find_refer_skills.py")
SKILL_DIR = Path(__file__).resolve().parent.parent


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

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired as error:
            self.fail(f"CLI 回归超过 30 秒硬时限: {error}")

    def test_discovers_standard_plugin_and_nested_skills_roots(self) -> None:
        self.write_skill("repo-a/skills/alpha/SKILL.md", "alpha", "Peer review of papers")
        self.write_skill("repo-b/plugins/demo/skills/beta/SKILL.md", "beta", "Scientific visualization")
        self.write_skill("repo-c/skills/skills/category/gamma/SKILL.md", "gamma", "Data analysis")
        self.write_skill("repo-a/other/ignored/SKILL.md", "ignored", "Must not be discovered")

        process = self.run_cli("--limit", "0")
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual({item["name"] for item in payload["matches"]}, {"alpha", "beta", "gamma"})
        self.assertEqual(payload["candidate_count"], 3)

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


if __name__ == "__main__":
    unittest.main()
