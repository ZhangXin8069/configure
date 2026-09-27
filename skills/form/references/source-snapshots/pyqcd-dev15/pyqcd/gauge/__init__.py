"""纯数组纯规范观测量。

本子包不包含费米子、MPI 或文件 IO；其输入是 PyQCD 统一的
``(Nt,Nz,Ny,Nx,4,3,3)`` 规范链接数组，输出由当前 NumPy/CuPy/torch
后端决定。拓扑 API 明确区分逐点密度、体积平均和总拓扑荷。
"""

from ._observables import (
    clover_field_strength,
    clover_topological_charge,
    clover_topological_charge_average,
    clover_topological_charge_density,
    clover_topological_charge_density_average,
    polyakov_loop,
    polyakov_loop_average,
    topological_charge,
    topological_charge_density,
    topological_charge_density_average,
    total_topological_charge,
    wilson_loop,
    wilson_rectangle,
)

__all__ = [
    "wilson_rectangle", "wilson_loop",
    "polyakov_loop", "polyakov_loop_average",
    "clover_field_strength",
    "clover_topological_charge_density", "clover_topological_charge",
    "clover_topological_charge_density_average",
    "clover_topological_charge_average",
    "topological_charge_density", "topological_charge",
    "total_topological_charge", "topological_charge_density_average",
]
