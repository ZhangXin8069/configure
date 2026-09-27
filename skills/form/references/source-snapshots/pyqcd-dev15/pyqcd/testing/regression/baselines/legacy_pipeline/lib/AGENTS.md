# AGENTS.md — agent/docker-v20260805/lib

`legacy_pipeline` 内自包含蒸馏/收缩框架，是 `refer/sush/lqcddb` 的冻结扁平快照
（逐字复制，**不 import**）。

## 模块

`backend.py`（后端切换）、`base_functions.py`（Levi-Civita、动量表、缓存 einsum）、`gamma_matrix.py`（DR γ 18 种）、`sigma_matrix.py`、`constants.py`、`baroperator.py`、`seqperam.py`、`autowick.py`、`dynamic.py`、`vertex.py`（VdV/VVV）、`analyse.py`、`io_readers.py`、`__init__.py`。

## 约定

- **禁止从 `refer/sush/` import**——本目录是用于回归的冻结自包含副本
- 新模块/图/输出属于流水线自身 `output/`，不放这里
