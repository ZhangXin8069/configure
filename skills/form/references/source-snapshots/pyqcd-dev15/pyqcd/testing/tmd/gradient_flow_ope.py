#!/usr/bin/env python3
"""生成一个参考 schema-v2 梯度流胶子 OPE artifact。"""
from __future__ import annotations

import argparse

from pyqcd.pipeline import run_gradient_flow_gluon_ope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="ILDG .lime 或 .lime.contents")
    parser.add_argument("--conf-id", required=True)
    parser.add_argument("--output", required=True, help="输出 base，不带 .npy/.json")
    parser.add_argument("--nx", required=True, type=int)
    parser.add_argument("--ny", type=int)
    parser.add_argument("--nz", type=int)
    parser.add_argument("--nt", required=True, type=int)
    parser.add_argument("--tau", required=True, type=float)
    parser.add_argument("--epsilon", default=0.01, type=float)
    parser.add_argument("--z-count", default=25, type=int)
    parser.add_argument("--z-dir", default=2, type=int)
    args = parser.parse_args()

    for name in ("ny", "nz"):
        value = getattr(args, name)
        if value is not None and value != args.nx:
            parser.error("当前 reader 要求 nx=ny=nz")
    run_gradient_flow_gluon_ope(
        args.input, args.output, nt=args.nt, nx=args.nx,
        tau=args.tau, conf_id=args.conf_id, epsilon=args.epsilon,
        z_count=args.z_count, z_dir=args.z_dir,
    )


if __name__ == "__main__":
    main()
