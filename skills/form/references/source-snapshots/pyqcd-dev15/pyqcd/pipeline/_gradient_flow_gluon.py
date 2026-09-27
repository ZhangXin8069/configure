"""参考 donghx schema-v2 单组态梯度流胶子 OPE 驱动。"""
from __future__ import annotations

import os

from ..operator import read_gauge_lime
from ..operator._gradient_flow_gluon_ope import (
    gradient_flow_gluon_ope,
    save_gradient_flow_gluon_ope,
)


def run_gradient_flow_gluon_ope(
        input_path, output_base, *, nt, nx, tau, conf_id=None,
        epsilon=0.01, z_count=25, z_dir=2, logger=print):
    """读取一个 ILDG 组态并生成配对 schema-v2 ``.npy/.json``。

    当前 ILDG reader 与参考生产程序一样面向各向同性空间格点；
    ``nx`` 是空间边长，``nt`` 是时间边长。输入文件也可以是
    ``.lime.contents`` 目录。
    """
    if conf_id is None:
        conf_id = "unknown"
    logger(
        f"LOAD conf={conf_id} input={os.fspath(input_path)} "
        f"lattice={int(nx)}^3x{int(nt)}"
    )
    gauge = read_gauge_lime(os.fspath(input_path), int(nt), int(nx))
    data, metadata = gradient_flow_gluon_ope(
        gauge, tau=tau, epsilon=epsilon, z_count=z_count,
        z_dir=z_dir, conf_id=conf_id,
    )
    paths = save_gradient_flow_gluon_ope(output_base, data, metadata)
    logger(
        f"OUTPUT conf={conf_id} schema={metadata['schema']} "
        f"shape={data.shape} npy={paths[0]} json={paths[1]}"
    )
    return data, metadata


__all__ = ["run_gradient_flow_gluon_ope"]
