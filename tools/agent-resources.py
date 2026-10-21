#!/usr/bin/env python3
"""Emit a conservative, read-only resource snapshot for agent planning.

The design is adapted from scientific-agent-skills/get-available-resources
(K-Dense Inc., MIT, fixed commit 593377bb048752abb0152deab9fbb1083a6087df),
but this is a smaller standard-library implementation for configure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional


MAX_TEXT_BYTES = 64 * 1024
SLURM_ENV_KEYS = (
    "SLURM_CPUS_PER_TASK",
    "SLURM_CPUS_ON_NODE",
    "SLURM_MEM_PER_NODE",
    "SLURM_MEM_PER_CPU",
    "SLURM_GPUS",
    "SLURM_GPUS_ON_NODE",
    "SLURM_JOB_PARTITION",
)


def _read_text(path: Path, warnings: List[str], code: str) -> Optional[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(MAX_TEXT_BYTES)
    except OSError:
        warnings.append(code)
        return None


def _int_or_none(value: object) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_cpu_list(value: Optional[str]) -> Optional[int]:
    """Return the number of CPUs represented by a Linux CPU list."""
    if not value:
        return None
    total = 0
    try:
        for part in value.strip().split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start, end = int(start_text), int(end_text)
                if end < start:
                    return None
                total += end - start + 1
            else:
                int(part)
                total += 1
    except ValueError:
        return None
    return total or None


def parse_cpu_max(value: Optional[str]) -> Optional[float]:
    """Parse cgroup v2 cpu.max into CPU-time capacity."""
    if not value:
        return None
    fields = value.strip().split()
    if len(fields) != 2 or fields[0] == "max":
        return None
    quota = _int_or_none(fields[0])
    period = _int_or_none(fields[1])
    if quota is None or period in (None, 0):
        return None
    return round(quota / period, 3)


def parse_meminfo(value: Optional[str]) -> Dict[str, Optional[int]]:
    result: Dict[str, Optional[int]] = {
        "total_bytes": None,
        "available_bytes": None,
    }
    if not value:
        return result
    for line in value.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        key = fields[0].rstrip(":")
        amount = _int_or_none(fields[1])
        if amount is None:
            continue
        if key == "MemTotal":
            result["total_bytes"] = amount * 1024
        elif key == "MemAvailable":
            result["available_bytes"] = amount * 1024
    return result


def _read_int_file(path: Path) -> Optional[int]:
    try:
        value = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return _int_or_none(value)


def _min_known(values: Iterable[Optional[float]]) -> Optional[float]:
    known = [value for value in values if value is not None and value > 0]
    return min(known) if known else None


def _slurm_allocation(env: Dict[str, str], warnings: List[str]) -> Dict[str, object]:
    present = any(key in env for key in SLURM_ENV_KEYS) or "SLURM_JOB_ID" in env
    cpus_per_task = _int_or_none(env.get("SLURM_CPUS_PER_TASK"))
    cpus_on_node = _int_or_none(env.get("SLURM_CPUS_ON_NODE"))
    memory_per_node = _int_or_none(env.get("SLURM_MEM_PER_NODE"))
    memory_per_cpu = _int_or_none(env.get("SLURM_MEM_PER_CPU"))
    memory_mib = memory_per_node
    if memory_mib is None and memory_per_cpu is not None and cpus_per_task is not None:
        memory_mib = memory_per_cpu * cpus_per_task
    if "SLURM_MEM_PER_NODE" in env and memory_per_node is None:
        warnings.append("slurm_memory_parse_failed")
    return {
        "detected": present,
        "name": "slurm" if present else None,
        "cpu_per_task": cpus_per_task,
        "cpus_on_node": cpus_on_node,
        "memory_mib": memory_mib,
        "gpus": env.get("SLURM_GPUS_ON_NODE") or env.get("SLURM_GPUS"),
        "partition": env.get("SLURM_JOB_PARTITION"),
    }


def _probe_nvidia(warnings: List[str]) -> Optional[Dict[str, object]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    command = [
        executable,
        "--query-gpu=memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        warnings.append("nvidia_probe_failed")
        return None
    if completed.returncode != 0:
        warnings.append("nvidia_probe_failed")
        return None
    memories = []
    for line in completed.stdout.splitlines()[:64]:
        memory = _int_or_none(line.strip())
        if memory is not None:
            memories.append(memory)
    return {
        "backend": "nvidia",
        "candidate_count": len(memories),
        "reported_total_mib": memories,
        "runtime_compatibility": "not_tested",
    }


def collect_snapshot(
    proc_root: Path,
    cgroup_root: Path,
    workdir: Path,
    env: Optional[Dict[str, str]] = None,
    affinity_count: Optional[int] = None,
    logical_cpu_count: Optional[int] = None,
    probe_accelerators: bool = True,
) -> Dict[str, object]:
    env = dict(os.environ if env is None else env)
    warnings: List[str] = []
    provenance: List[Dict[str, str]] = []

    if logical_cpu_count is None:
        cpuinfo = _read_text(proc_root / "cpuinfo", warnings, "proc_cpuinfo_unavailable")
        if cpuinfo:
            logical_cpu_count = sum(1 for line in cpuinfo.splitlines() if line.startswith("processor"))
            provenance.append({"source": "proc_cpuinfo", "status": "ok"})
    if logical_cpu_count is None:
        logical_cpu_count = os.cpu_count()
    if affinity_count is None and hasattr(os, "sched_getaffinity"):
        try:
            affinity_count = len(os.sched_getaffinity(0))
            provenance.append({"source": "process_affinity", "status": "ok"})
        except OSError:
            warnings.append("process_affinity_unavailable")

    cpuset_text = _read_text(
        cgroup_root / "cpuset.cpus.effective", warnings, "cgroup_cpuset_unavailable"
    )
    cgroup_cpus = parse_cpu_list(cpuset_text)
    if cgroup_cpus is not None:
        provenance.append({"source": "cgroup_cpuset", "status": "ok"})
    cpu_max_text = _read_text(cgroup_root / "cpu.max", warnings, "cgroup_cpu_max_unavailable")
    quota_cores = parse_cpu_max(cpu_max_text)
    if quota_cores is not None:
        provenance.append({"source": "cgroup_cpu_quota", "status": "ok"})

    slurm = _slurm_allocation(env, warnings)
    cpu_candidates = [
        float(value)
        for value in (affinity_count, cgroup_cpus, quota_cores, slurm["cpu_per_task"])
        if value is not None and value > 0
    ]
    capacity_cores = min(cpu_candidates) if cpu_candidates else None
    worker_ceiling = int(capacity_cores) if capacity_cores is not None else None

    meminfo_text = _read_text(proc_root / "meminfo", warnings, "proc_meminfo_unavailable")
    meminfo = parse_meminfo(meminfo_text)
    if meminfo_text:
        provenance.append({"source": "proc_meminfo", "status": "ok"})
    cgroup_memory_max = _read_int_file(cgroup_root / "memory.max")
    cgroup_memory_current = _read_int_file(cgroup_root / "memory.current")
    cgroup_memory_high = _read_int_file(cgroup_root / "memory.high")
    if cgroup_memory_max is not None:
        provenance.append({"source": "cgroup_memory", "status": "ok"})
    slurm_memory_bytes = None
    if isinstance(slurm["memory_mib"], int):
        slurm_memory_bytes = slurm["memory_mib"] * 1024 * 1024
    container_markers = []
    if Path("/.dockerenv").exists():
        container_markers.append("docker")
    if Path("/run/.containerenv").exists():
        container_markers.append("container")
    if "container" in env:
        container_markers.append("container_env")
    isolation_active = bool(container_markers) or bool(slurm["detected"])
    host_memory_candidates = [] if isolation_active else [meminfo["total_bytes"]]
    memory_limit = _min_known(host_memory_candidates + [cgroup_memory_max, slurm_memory_bytes])
    cgroup_remaining = None
    if cgroup_memory_max is not None and cgroup_memory_current is not None:
        cgroup_remaining = max(cgroup_memory_max - cgroup_memory_current, 0)
    host_available_candidates = [] if isolation_active else [meminfo["available_bytes"]]
    memory_available = _min_known(
        host_available_candidates + [cgroup_remaining, slurm_memory_bytes]
    )
    review_required = (
        (bool(container_markers) and cgroup_memory_max is None)
        or (bool(slurm["detected"]) and slurm_memory_bytes is None)
    )

    try:
        disk = shutil.disk_usage(workdir)
        disk_snapshot: Dict[str, object] = {
            "role": "workspace",
            "capacity_bytes": disk.total,
            "free_bytes": disk.free,
        }
        provenance.append({"source": "workspace_disk", "status": "ok"})
    except OSError:
        warnings.append("workspace_disk_unavailable")
        disk_snapshot = {
            "role": "workspace",
            "capacity_bytes": None,
            "free_bytes": None,
        }

    accelerators: Dict[str, object] = {
        "candidates": [],
        "runtime_usable_devices": None,
        "note": "management visibility does not establish scheduler permission or runtime compatibility",
    }
    if probe_accelerators:
        nvidia = _probe_nvidia(warnings)
        if nvidia and nvidia["candidate_count"]:
            accelerators["candidates"] = [nvidia]
            provenance.append({"source": "nvidia_smi", "status": "ok"})
    if "CUDA_VISIBLE_DEVICES" in env:
        accelerators["cuda_visible_override"] = {
            "present": True,
            "disabled": env.get("CUDA_VISIBLE_DEVICES") == "-1",
        }

    return {
        "schema_version": "1",
        "observed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "platform": {
            "system": platform.system().lower(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "cpu": {
            "host_logical": logical_cpu_count,
            "process_affinity_logical": affinity_count,
            "cgroup_cpuset_logical": cgroup_cpus,
            "cgroup_quota_cores": quota_cores,
            "scheduler_cpu_per_task": slurm["cpu_per_task"],
            "effective_capacity_cores": capacity_cores,
            "worker_ceiling": worker_ceiling,
        },
        "memory": {
            "host_total_bytes": meminfo["total_bytes"],
            "host_available_bytes": meminfo["available_bytes"],
            "cgroup_current_bytes": cgroup_memory_current,
            "cgroup_max_bytes": cgroup_memory_max,
            "cgroup_high_bytes": cgroup_memory_high,
            "scheduler_limit_bytes": slurm_memory_bytes,
            "effective_limit_bytes": memory_limit,
            "available_estimate_bytes": memory_available,
        },
        "disk": disk_snapshot,
        "scheduler": slurm,
        "container_markers": sorted(set(container_markers)),
        "review_required": review_required,
        "accelerators": accelerators,
        "completeness": "partial" if warnings else "complete",
        "warnings": sorted(set(warnings)),
        "provenance": sorted(provenance, key=lambda item: item["source"]),
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a conservative, redacted agent resource snapshot as JSON."
    )
    parser.add_argument("--proc-root", default="/proc", help="read-only procfs root")
    parser.add_argument("--cgroup-root", default="/sys/fs/cgroup", help="cgroup v2 root")
    parser.add_argument("--workdir", default=".", help="filesystem to report for workspace disk")
    parser.add_argument("--no-accelerators", action="store_true", help="skip accelerator probes")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    snapshot = collect_snapshot(
        proc_root=Path(args.proc_root),
        cgroup_root=Path(args.cgroup_root),
        workdir=Path(args.workdir),
        probe_accelerators=not args.no_accelerators,
    )
    json.dump(
        snapshot,
        sys.stdout,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":") if args.compact else None,
        indent=None if args.compact else 2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
