#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("agent-resources.py")
SPEC = importlib.util.spec_from_file_location("agent_resources", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ResourceParserTests(unittest.TestCase):
    def test_parse_cpu_list(self):
        self.assertEqual(MODULE.parse_cpu_list("0-3,8,10-11"), 7)
        self.assertIsNone(MODULE.parse_cpu_list("4-1"))
        self.assertIsNone(MODULE.parse_cpu_list(""))

    def test_parse_cpu_max(self):
        self.assertEqual(MODULE.parse_cpu_max("200000 100000"), 2.0)
        self.assertEqual(MODULE.parse_cpu_max("50000 100000"), 0.5)
        self.assertIsNone(MODULE.parse_cpu_max("max 100000"))
        self.assertIsNone(MODULE.parse_cpu_max("bad 100000"))

    def test_parse_gpu_count(self):
        self.assertEqual(MODULE.parse_gpu_count("2"), 2)
        self.assertEqual(MODULE.parse_gpu_count("gpu:2(S:0-1)"), 2)
        self.assertEqual(MODULE.parse_gpu_count("a100:1,gpu:2"), 3)
        self.assertIsNone(MODULE.parse_gpu_count("gpu:secret"))


class SnapshotTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        proc = root / "proc"
        cgroup = root / "cgroup"
        work = root / "work"
        proc.mkdir()
        cgroup.mkdir()
        work.mkdir()
        (proc / "cpuinfo").write_text("processor\t: 0\nprocessor\t: 1\n", encoding="utf-8")
        (proc / "meminfo").write_text(
            "MemTotal:       16777216 kB\nMemAvailable:    4194304 kB\n",
            encoding="utf-8",
        )
        (cgroup / "cpuset.cpus.effective").write_text("0-3\n", encoding="ascii")
        (cgroup / "cpu.max").write_text("200000 100000\n", encoding="ascii")
        (cgroup / "memory.max").write_text(str(8 * 1024**3), encoding="ascii")
        (cgroup / "memory.current").write_text(str(1024**3), encoding="ascii")
        (cgroup / "memory.high").write_text(str(7 * 1024**3), encoding="ascii")
        return proc, cgroup, work

    def test_collects_effective_limits_without_sensitive_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proc, cgroup, work = self._fixture(root)
            env = {
                "SLURM_CPUS_PER_TASK": "3",
                "SLURM_MEM_PER_NODE": "6144",
                "SLURM_GPUS_ON_NODE": "gpu:2",
                "SLURM_JOB_PARTITION": "sensitive-partition-name",
                "SLURM_JOB_ID": "sensitive-job-id",
                "CUDA_VISIBLE_DEVICES": "0,1",
            }
            snapshot = MODULE.collect_snapshot(
                proc_root=proc,
                cgroup_root=cgroup,
                workdir=work,
                env=env,
                affinity_count=6,
                logical_cpu_count=8,
                probe_accelerators=False,
                container_markers_override=["docker"],
            )
            self.assertEqual(snapshot["cpu"]["effective_capacity_cores"], 2.0)
            self.assertEqual(snapshot["cpu"]["worker_ceiling"], 2)
            self.assertEqual(snapshot["memory"]["effective_limit_bytes"], 6 * 1024**3)
            self.assertEqual(snapshot["memory"]["available_estimate_bytes"], 7 * 1024**3)
            self.assertTrue(snapshot["scheduler"]["detected"])
            self.assertEqual(snapshot["scheduler"]["cpu_per_task"], 3)
            self.assertEqual(snapshot["scheduler"]["gpu_count"], 2)
            self.assertTrue(snapshot["scheduler"]["partition_present"])
            self.assertTrue(snapshot["scheduler"]["job_id_present"])
            self.assertFalse(snapshot["review_required"])
            self.assertEqual(snapshot["accelerators"]["runtime_usable_devices"], None)
            self.assertTrue(snapshot["accelerators"]["cuda_visible_override"]["present"])
            serialized = json.dumps(snapshot)
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("hostname", serialized)
            self.assertNotIn("sensitive-partition-name", serialized)
            self.assertNotIn("sensitive-job-id", serialized)

    def test_missing_observations_remain_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = MODULE.collect_snapshot(
                proc_root=root / "missing-proc",
                cgroup_root=root / "missing-cgroup",
                workdir=root,
                env={},
                affinity_count=0,
                logical_cpu_count=None,
                probe_accelerators=False,
                container_markers_override=[],
            )
            self.assertIsNone(snapshot["memory"]["effective_limit_bytes"])
            self.assertIsNone(snapshot["cpu"]["effective_capacity_cores"])
            self.assertEqual(snapshot["completeness"], "partial")
            self.assertIn("proc_meminfo_unavailable", snapshot["warnings"])
            self.assertTrue(snapshot["review_required"])
            self.assertIn("cpu_capacity_unknown", snapshot["review_reasons"])
            self.assertNotIn("unlimited", json.dumps(snapshot).lower())

    def test_nvidia_probe_bounds_parsed_output(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp)
            fake = bin_dir / "nvidia-smi"
            fake.write_text(
                "#!/usr/bin/env bash\nfor _ in $(seq 1 100); do printf '1024\\n'; done\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            warnings = []
            with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}):
                result = MODULE._probe_nvidia(warnings)
            self.assertIsNotNone(result)
            self.assertEqual(result["candidate_count"], 64)
            self.assertEqual(len(result["reported_total_mib"]), 64)
            self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
