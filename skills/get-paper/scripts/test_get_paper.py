#!/usr/bin/env python3
"""Offline regression tests for get-paper.py."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("get-paper.py")
REPO_DATA = Path(__file__).resolve().parents[3] / "data"
SPEC = importlib.util.spec_from_file_location("get_paper", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class GetPaperTests(unittest.TestCase):
    def test_identifier_parsing(self) -> None:
        self.assertEqual(MODULE.arxiv_id_from_text("https://arxiv.org/src/2601.01205"), "2601.01205")
        self.assertEqual(MODULE.arxiv_id_from_text("arXiv:hep-th/9901001v2"), "hep-th/9901001v2")
        self.assertEqual(
            MODULE.doi_from_text("https://doi.org/10.1103/c66h-96wh"),
            "10.1103/c66h-96wh",
        )
        self.assertIsNone(MODULE.arxiv_id_from_text("https://doi.org/10.5555/2024.12345"))
        self.assertEqual(
            MODULE.arxiv_id_from_text("https://doi.org/10.48550/arXiv.2601.01205"),
            "2601.01205",
        )

    def test_relevance_prefers_task_specific_title(self) -> None:
        task = "lattice QCD pi K scattering length from moving frames"
        relevant = MODULE.relevance_score(
            task,
            "pi K scattering length from lattice QCD",
            "Moving-frame correlation functions are analyzed.",
        )
        unrelated = MODULE.relevance_score(
            task,
            "Galaxy morphology in deep surveys",
            "A catalog of distant galaxies.",
        )
        self.assertGreater(relevant, unrelated)
        self.assertGreater(relevant, 0.5)
        greek = MODULE.relevance_score(
            task,
            "S-wave πK scattering length from lattice QCD",
            "Moving frames are used.",
        )
        self.assertGreater(greek, unrelated)

    def test_deduplication_merges_source_provenance(self) -> None:
        first = MODULE.Paper(title="A Paper", doi="10.1/example", sources=["crossref"])
        second = MODULE.Paper(
            title="A Paper",
            doi="10.1/example",
            arxiv_id="2601.01205",
            abstract="A longer abstract.",
            sources=["arxiv"],
        )
        merged = MODULE.deduplicate([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].sources), {"arxiv", "crossref"})
        self.assertEqual(merged[0].arxiv_id, "2601.01205")

    def test_title_only_deduplication_requires_year_and_author(self) -> None:
        left = MODULE.Paper(title="Introduction", year=2020, authors=["Alice Smith"])
        right = MODULE.Paper(title="Introduction", year=2024, authors=["Bob Jones"])
        self.assertEqual(len(MODULE.deduplicate([left, right])), 2)

    def test_openalex_abstract_reconstruction(self) -> None:
        index = {"safe": [0, 2], "source": [1], "text": [3]}
        self.assertEqual(MODULE.reconstruct_openalex_abstract(index), "safe source safe text")

    def test_openalex_non_oa_location_is_not_exposed_as_download(self) -> None:
        record = {
            "id": "https://openalex.org/W1",
            "display_name": "Closed paper",
            "is_oa": False,
            "best_oa_location": {"pdf_url": "https://example.org/closed.pdf", "is_oa": False},
        }
        paper = MODULE.openalex_to_paper(record)
        self.assertIsNone(paper.pdf_url)
        self.assertIsNone(paper.oa_url)

    def test_main_tex_detection(self) -> None:
        REPO_DATA.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            root = Path(temporary)
            (root / "fragment.tex").write_text(
                "\\documentclass{article}\n\\begin{document}Fragment\\end{document}\n",
                encoding="utf-8",
            )
            (root / "paper.tex").write_text(
                "\\documentclass{article}\n\\begin{document}\nBody\n\\end{document}\n",
                encoding="utf-8",
            )
            self.assertEqual(MODULE.find_main_tex(root), "paper.tex")
            (root / "paper.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            self.assertEqual(MODULE.find_main_tex(root), "fragment.tex")

    def test_fragment_is_not_main_tex(self) -> None:
        REPO_DATA.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            root = Path(temporary)
            (root / "fragment.tex").write_text("\\section{Fragment}\n", encoding="utf-8")
            self.assertIsNone(MODULE.find_main_tex(root))

    def test_extract_tar_and_reject_path_traversal(self) -> None:
        REPO_DATA.mkdir(exist_ok=True)
        safe_buffer = io.BytesIO()
        with tarfile.open(fileobj=safe_buffer, mode="w:gz") as archive:
            content = b"\\documentclass{article}\n\\begin{document}x\\end{document}\n"
            info = tarfile.TarInfo("source/main.tex")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            result = MODULE.extract_artifact(
                safe_buffer.getvalue(),
                content_type="application/gzip",
                destination=Path(temporary) / "source",
                max_bytes=1024 * 1024,
                max_files=100,
            )
            self.assertEqual(result["kind"], "tar")
            self.assertEqual(result["main_tex"], "source/main.tex")

        unsafe_buffer = io.BytesIO()
        with tarfile.open(fileobj=unsafe_buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("../escape.tex")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            with self.assertRaises(MODULE.UnsafeArchiveError):
                MODULE.extract_artifact(
                    unsafe_buffer.getvalue(),
                    content_type="application/gzip",
                    destination=Path(temporary) / "source",
                    max_bytes=1024 * 1024,
                    max_files=100,
                )

    def test_archive_rejects_absolute_paths(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("/absolute.tex")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            with self.assertRaises(MODULE.UnsafeArchiveError):
                MODULE.extract_artifact(
                    buffer.getvalue(),
                    content_type="application/gzip",
                    destination=Path(temporary) / "source",
                    max_bytes=1024,
                    max_files=10,
                )

    def test_failed_replacement_preserves_existing_artifact(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("../escape.tex")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            destination = Path(temporary) / "source"
            destination.mkdir()
            (destination / "old.tex").write_text("old", encoding="utf-8")
            with self.assertRaises(MODULE.UnsafeArchiveError):
                MODULE.extract_artifact(
                    buffer.getvalue(),
                    content_type="application/gzip",
                    destination=destination,
                    max_bytes=1024,
                    max_files=10,
                    replace=True,
                )
            self.assertTrue((destination / "old.tex").is_file())

    def test_pdf_fallback_creates_source_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            destination = Path(temporary) / "paper" / "source"
            metadata = {
                "url": "https://example.org/paper.pdf",
                "status": "200",
                "content_type": "application/pdf",
            }
            with mock.patch.object(MODULE, "request_bytes", return_value=(b"%PDF-1.4\n", metadata)):
                result = MODULE.download_pdf("https://example.org/paper.pdf", destination, force=False)
            self.assertEqual(result["kind"], "pdf")
            self.assertTrue((destination / "paper.pdf").is_file())

    def test_unknown_artifact_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            with self.assertRaises(MODULE.GetPaperError):
                MODULE.extract_artifact(
                    b'{"error":"not a paper"}',
                    content_type="application/json",
                    destination=Path(temporary) / "source",
                    max_bytes=1024,
                    max_files=10,
                )

    def test_compact_query_removes_stopwords(self) -> None:
        query = MODULE.compact_query("We study the lattice QCD scattering length using moving frames")
        self.assertIn("lattice", query)
        self.assertIn("scattering", query)
        self.assertNotIn("the", query.split())
        tokens = MODULE.tokenize("I=3/2 πK scattering")
        self.assertIn("3-2", tokens)
        self.assertIn("pi", tokens)
        self.assertIn("k", tokens)

    def test_arxiv_query_uses_phrase_then_boolean_fallback(self) -> None:
        expressions = MODULE.arxiv_search_expressions("pi K scattering length lattice QCD")
        self.assertEqual(expressions[0], 'all:"pi K scattering length lattice QCD"')
        self.assertEqual(expressions[1], 'all:"pi k scattering length"')
        self.assertIn("all:pi AND", expressions[2])
        explicit = MODULE.arxiv_search_expressions('all:"pi K" AND all:"lattice QCD"')
        self.assertEqual(explicit, ['all:"pi K" AND all:"lattice QCD"'])

    def test_source_failure_does_not_stop_later_sources_or_leak_mailto(self) -> None:
        def bad_source(_query: str, _limit: int) -> list[object]:
            raise TypeError("failed https://example.org/search?mailto=private@example.org")

        def good_source(_query: str, _limit: int) -> list[object]:
            return [MODULE.Paper(title="Relevant paper", authors=["Alice Smith"], year=2026)]

        with mock.patch.dict(
            MODULE.SEARCH_ADAPTERS,
            {"bad": bad_source, "good": good_source},
            clear=True,
        ):
            payload = MODULE.search_sources("relevant paper", "relevant paper", ["bad", "good"], 5)
        self.assertFalse(payload["sources"]["bad"]["ok"])
        self.assertTrue(payload["sources"]["good"]["ok"])
        self.assertEqual(len(payload["results"]), 1)
        self.assertNotIn("private@example.org", json.dumps(payload))

    def test_cached_payload_is_reusable_offline_and_reanalyzes_task(self) -> None:
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            output_root = Path(temporary)
            destination = output_root / MODULE.folder_for_identifier("arXiv:2601.01205")
            source = destination / "source"
            source.mkdir(parents=True)
            (source / "main.tex").write_text(
                "\\documentclass{article}\n\\begin{document}x\\end{document}\n",
                encoding="utf-8",
            )
            payload = {
                "schema_version": 1,
                "identifier": "arXiv:2601.01205",
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "task": "old task",
                "paper": {
                    "title": "pi K scattering from lattice QCD",
                    "abstract": "A moving-frame calculation.",
                },
                "artifact": {
                    "files": ["main.tex"],
                    "main_tex": "main.tex",
                    "tree_sha256": MODULE.directory_digest(source),
                },
            }
            (destination / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(MODULE, "metadata_for_identifier", side_effect=AssertionError("network used")):
                cached = MODULE.fetch_paper(
                    "arXiv:2601.01205",
                    output_root,
                    task="pi K scattering lattice QCD",
                    pdf_fallback=True,
                    force=False,
                    max_extract_bytes=1024,
                    max_files=10,
                )
            self.assertTrue(cached["reused"])
            self.assertEqual(cached["task"], "pi K scattering lattice QCD")
            self.assertGreater(cached["relevance_score"], 0)

    def test_cache_rejects_tampered_source_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="get-paper-test-", dir=REPO_DATA) as temporary:
            destination = Path(temporary) / "paper"
            source = destination / "source"
            source.mkdir(parents=True)
            (source / "main.tex").write_text("original", encoding="utf-8")
            payload = {
                "schema_version": 1,
                "paper": {"title": "Paper"},
                "artifact": {
                    "files": ["main.tex"],
                    "main_tex": "main.tex",
                    "tree_sha256": MODULE.directory_digest(source),
                },
            }
            (destination / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
            (source / "main.tex").write_text("tampered", encoding="utf-8")
            with self.assertRaises(MODULE.GetPaperError):
                MODULE.load_cached_payload(destination, "task")

    def test_non_http_and_private_urls_are_rejected(self) -> None:
        for url in ("file:///tmp/paper.pdf", "http://127.0.0.1/paper.pdf", "http://localhost/paper.pdf"):
            with self.subTest(url=url), self.assertRaises(MODULE.NetworkError):
                MODULE.validate_remote_url(url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
