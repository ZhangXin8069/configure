from argparse import Namespace
"""工具层：GPU/CPU 后端切换（numpy/cupy/torch）、缓存 einsum、数组切片、I/O 读取。"""
from ._backend import (
    set_backend, get_backend, get_backend_name, get_torch_device,
    set_precision, get_precision,
)
from ._env import dump_env
from ._base import cached_contract, clear_cache, ArraySlicer, levi_civita_tensor, creat_mom_list
from ._io import (
    readin_eigvecs, readin_eigvecs_gpu, readin_eigvecs_tensor,
    readin_peram, readin_peram_time_slice,
    readin_vdv_all, readin_vvv_all, readin_vvv,
    safe_save, check_dir_path,
    save_tensor_h5, load_tensor_h5,
    write_data_ascii, read_data_ascii,
)

__all__ = [
    "dump_env",
    "set_backend", "get_backend", "get_backend_name", "get_torch_device",
    "set_precision", "get_precision",
    "cached_contract", "clear_cache", "ArraySlicer", "levi_civita_tensor", "creat_mom_list",
    "readin_eigvecs", "readin_eigvecs_gpu", "readin_eigvecs_tensor",
    "readin_peram", "readin_peram_time_slice",
    "readin_vdv_all", "readin_vvv_all", "readin_vvv",
    "safe_save", "check_dir_path",
    "save_tensor_h5", "load_tensor_h5",
    "write_data_ascii", "read_data_ascii",
]

Namespace.__module__ = "pyqcd.tools"
