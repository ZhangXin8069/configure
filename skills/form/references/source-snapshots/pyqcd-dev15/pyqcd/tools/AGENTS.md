# AGENTS.md — pyqcd/tools

后端切换（numpy/cupy/torch）、缓存 einsum、切片工具、IO 读取。
L.Liu ASCII 关联函数读写（`_io.write_data_ascii/read_data_ascii`，.gz 自动压缩）；torch 适配层含 numpy-like 数学函数全集（cos/sin/arccos/isnan/clip/maximum
（接受标量）/argwhere/identity/append/random 等）。禁止直接 import cupy 计算
（仅 try/except 探测）。
V†V/VVV 预计算顶点积二进制 reader（`_io.readin_vdv_all/readin_vvv_all/readin_vvv`，
f8 交错复数，Nev 自探测+截断 Nev1）；运行环境快照 `dump_env(path)`（env.json：
git/包版本/xelatex/GPU/cmdline）。
