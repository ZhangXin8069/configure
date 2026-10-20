#!/usr/bin/env python3
"""Offline regression tests for absorb_inventory.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("absorb_inventory.py")
REPO_DATA = Path(__file__).resolve().parents[3] / "data"
SPEC = importlib.util.spec_from_file_location("absorb_inventory", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def git(root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process.stdout.strip()


class AbsorbInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        REPO_DATA.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="absorb-test-", dir=REPO_DATA)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "Test Agent")
        git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-q", "-m", "base")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def candidates_for(self, payload: dict[str, object], path: str) -> list[dict[str, object]]:
        return [candidate for candidate in payload["candidates"] if candidate["path"] == path]

    def test_inventory_covers_commit_staged_untracked_and_symlink(self) -> None:
        foreign = self.root / "refer" / "demo"
        foreign.mkdir(parents=True)
        (foreign / "LICENSE").write_text("MIT License\nCopyright (c) Example\n", encoding="utf-8")
        (foreign / "README.md").write_text(
            "Vendored from https://example.invalid/upstream\n",
            encoding="utf-8",
        )
        git(self.root, "add", "refer/demo")
        git(self.root, "commit", "-q", "-m", "add foreign reference")

        staged = self.root / "third_party" / "helper.py"
        staged.parent.mkdir(parents=True)
        staged.write_text('api_key = "abcdefghijk"\nsubprocess.run(["echo", "x"])\n', encoding="utf-8")
        git(self.root, "add", "third_party/helper.py")

        (self.root / "notes.txt").write_text("untrusted notes\n", encoding="utf-8")
        os.symlink("README.md", self.root / "linked-readme")

        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD^",
            scope="all",
            max_scan_bytes=1024 * 1024,
        )
        by_path = {candidate["path"]: candidate for candidate in payload["candidates"]}
        self.assertIn("refer/demo/LICENSE", by_path)
        self.assertIn("commits", by_path["refer/demo/README.md"]["scopes"])
        self.assertEqual(by_path["refer/demo/README.md"]["origin_hint"], "likely-foreign")
        self.assertIn("staged", by_path["third_party/helper.py"]["scopes"])
        risk_types = {signal["type"] for signal in by_path["third_party/helper.py"]["risk_signals"]}
        self.assertIn("secret-like", risk_types)
        self.assertIn("dynamic-execution", risk_types)
        self.assertIn("untracked", by_path["notes.txt"]["scopes"])
        symlink_risks = {signal["type"] for signal in by_path["linked-readme"]["risk_signals"]}
        self.assertIn("symlink", symlink_risks)
        encoded = json.dumps(payload)
        self.assertNotIn("abcdefghijk", encoded)

    def test_worktree_scope_excludes_committed_only_content(self) -> None:
        committed = self.root / "vendor" / "old.txt"
        committed.parent.mkdir()
        committed.write_text("committed\n", encoding="utf-8")
        git(self.root, "add", "vendor/old.txt")
        git(self.root, "commit", "-q", "-m", "vendor")
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD^",
            scope="worktree",
            max_scan_bytes=1024,
        )
        paths = {candidate["path"] for candidate in payload["candidates"]}
        self.assertNotIn("vendor/old.txt", paths)
        self.assertIn("new.txt", paths)

    def test_empty_repository_is_supported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="absorb-empty-test-", dir=REPO_DATA) as temporary:
            root = Path(temporary)
            git(root, "init", "-q")
            payload = MODULE.build_inventory(
                root,
                base_requested="auto",
                scope="all",
                max_scan_bytes=1024,
            )
            self.assertEqual(payload["candidate_count"], 0)
            self.assertIsNone(payload["head"])

    def test_cli_rejects_output_outside_worktree(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.json"
        process = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--root",
                str(self.root),
                "--output",
                str(outside),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(process.returncode, 3)
        self.assertIn("必须位于目标 Git 工作树内", process.stderr)
        self.assertFalse(outside.exists())

    def test_large_candidate_marks_scan_truncated(self) -> None:
        large = self.root / "external" / "large.txt"
        large.parent.mkdir(parents=True)
        large.write_text("A" * 2048, encoding="utf-8")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=128,
        )
        candidate = next(item for item in payload["candidates"] if item["path"] == "external/large.txt")
        self.assertTrue(candidate["scan_truncated"])
        self.assertIn("scan-truncated", {signal["type"] for signal in candidate["risk_signals"]})

    def test_staged_blob_is_scanned_separately_from_worktree_edit(self) -> None:
        path = "third_party/index-only.py"
        staged = self.root / path
        staged.parent.mkdir(parents=True)
        staged.write_text("api_key=abcdefghijk\n", encoding="utf-8")
        git(self.root, "add", path)
        staged.write_text("clean = True\n", encoding="utf-8")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
        )
        candidates = self.candidates_for(payload, path)
        self.assertEqual({candidate["source"] for candidate in candidates}, {"index", "worktree"})
        index_candidate = next(candidate for candidate in candidates if candidate["source"] == "index")
        self.assertIn("secret-like", {signal["type"] for signal in index_candidate["risk_signals"]})
        self.assertNotEqual(
            next(candidate["sha256"] for candidate in candidates if candidate["source"] == "index"),
            next(candidate["sha256"] for candidate in candidates if candidate["source"] == "worktree"),
        )

    def test_committed_blob_and_worktree_edit_are_both_visible(self) -> None:
        path = "vendor/committed.py"
        committed = self.root / path
        committed.parent.mkdir(parents=True)
        committed.write_text("token=abcdefghijk\n", encoding="utf-8")
        git(self.root, "add", path)
        git(self.root, "commit", "-q", "-m", "vendor secret")
        committed.write_text("clean = True\n", encoding="utf-8")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD^",
            scope="all",
            max_scan_bytes=1024,
        )
        candidates = self.candidates_for(payload, path)
        self.assertEqual({candidate["source"] for candidate in candidates}, {"commit", "worktree"})
        commit_candidate = next(candidate for candidate in candidates if candidate["source"] == "commit")
        self.assertIn("secret-like", {signal["type"] for signal in commit_candidate["risk_signals"]})

    def test_gitlink_is_inventoried_with_target_oid(self) -> None:
        oid = "1" * 40
        git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{oid},vendor/submodule")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
        )
        candidate = self.candidates_for(payload, "vendor/submodule")[0]
        self.assertEqual(candidate["source"], "gitlink")
        self.assertEqual(candidate["object_id"], oid)
        self.assertIn("gitlink", {signal["type"] for signal in candidate["risk_signals"]})

    def test_symlink_target_value_is_redacted(self) -> None:
        marker = "secret-target-marker"
        os.symlink(marker, self.root / "opaque-link")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
        )
        candidate = self.candidates_for(payload, "opaque-link")[0]
        self.assertEqual(candidate["language"], "symlink")
        self.assertIsNotNone(candidate["sha256"])
        self.assertNotIn(marker, json.dumps(payload))

    def test_staged_type_change_to_symlink_is_included(self) -> None:
        path = "external/type-change"
        target = self.root / path
        target.parent.mkdir(parents=True)
        target.write_text("regular\n", encoding="utf-8")
        git(self.root, "add", path)
        git(self.root, "commit", "-q", "-m", "regular file")
        target.unlink()
        os.symlink("elsewhere", target)
        git(self.root, "add", path)
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
        )
        candidate = self.candidates_for(payload, path)[0]
        self.assertEqual(candidate["git_mode"], "120000")
        self.assertIn("symlink", {signal["type"] for signal in candidate["risk_signals"]})

    def test_ignored_content_requires_explicit_flag(self) -> None:
        (self.root / ".gitignore").write_text("vendor/\n", encoding="utf-8")
        ignored = self.root / "vendor" / "ignored.py"
        ignored.parent.mkdir()
        ignored.write_text("ignored\n", encoding="utf-8")
        default_payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
        )
        self.assertNotIn("vendor/ignored.py", {candidate["path"] for candidate in default_payload["candidates"]})
        included_payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
            include_ignored=True,
        )
        self.assertIn("vendor/ignored.py", {candidate["path"] for candidate in included_payload["candidates"]})

    def test_common_license_names_and_unquoted_secret_are_detected(self) -> None:
        (self.root / "LICENSE-MIT").write_text("MIT\n", encoding="utf-8")
        reuse = self.root / "LICENSES" / "Apache-2.0.txt"
        reuse.parent.mkdir()
        reuse.write_text("Apache\n", encoding="utf-8")
        secret = self.root / "external" / "settings.env"
        secret.parent.mkdir()
        secret.write_text("API_KEY=abcdefghijk\n", encoding="utf-8")
        payload = MODULE.build_inventory(
            self.root,
            base_requested="HEAD",
            scope="worktree",
            max_scan_bytes=1024,
        )
        license_candidate = self.candidates_for(payload, "LICENSE-MIT")[0]
        reuse_candidate = self.candidates_for(payload, "LICENSES/Apache-2.0.txt")[0]
        self.assertIn("license-file", {signal["type"] for signal in license_candidate["provenance_signals"]})
        self.assertIn("license-file", {signal["type"] for signal in reuse_candidate["provenance_signals"]})
        secret_candidate = self.candidates_for(payload, "external/settings.env")[0]
        self.assertIn("secret-like", {signal["type"] for signal in secret_candidate["risk_signals"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
