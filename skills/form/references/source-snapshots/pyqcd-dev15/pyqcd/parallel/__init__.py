"""pyqcd 并行子包：资源检测 + MPI 元任务调度（torch+mpi4py+h5py）。"""
from ._resources import detect_resources, cpu_threads, gpu_info
from ._mpi import (
    get_mpi_context, plan_parallel, format_plan, run_meta_task,
    run_parallel_pipeline, main,
)

__all__ = [
    "detect_resources", "cpu_threads", "gpu_info",
    "get_mpi_context", "plan_parallel", "format_plan",
    "run_meta_task", "run_parallel_pipeline", "main",
]
