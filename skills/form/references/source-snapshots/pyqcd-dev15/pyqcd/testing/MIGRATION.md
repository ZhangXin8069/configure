# `examples/` 到 `pyqcd/testing/` 迁移映射

迁移完成日期：2026-09-27。原 `examples/` 树已整体删除，不再保留并行入口。

| 旧路径 | 新路径 |
|---|---|
| `examples/_docker/` | `pyqcd/testing/regression/baselines/docker_support/` |
| `examples/docker-v20260805/` | `pyqcd/testing/regression/baselines/legacy_pipeline/` |
| `examples/test0/` | `pyqcd/testing/regression/distillation/` |
| `examples/test0/v*` | `pyqcd/testing/regression/distillation/artifacts/` |
| `examples/pyqcd/conftest.py` | `pyqcd/testing/conftest.py` |
| `examples/pyqcd/test_contracts.py` | `pyqcd/testing/test_contracts.py` |
| `examples/pyqcd/verify_consistency.py` | `pyqcd/testing/regression/consistency.py` |
| `examples/pyqcd/gevp_*.py` | `pyqcd/testing/regression/gevp/` |
| `examples/pyqcd/tmd_gradient_flow_demo.py` | `pyqcd/testing/demos/tmd_gradient_flow.py` |
| `examples/pyqcd/gradient_flow_gluon_ope.py` | `pyqcd/testing/tmd/gradient_flow_ope.py` |
| `examples/pyqcd/test9_gluon_tmd_nucleon.py` | `pyqcd/testing/tmd/pdf_workflow.py` |
| `examples/pyqcd/test9_verify.py` | `pyqcd/testing/tmd/verify_pdf_workflow.py` |
| `examples/pyqcd/test9/` | `pyqcd/testing/tmd/artifacts/initial_run/` |
| `examples/pyqcd/test9_1/` | `pyqcd/testing/tmd/artifacts/extended_run/` |
| `examples/pyqcd/test9_2/` | `pyqcd/testing/tmd/artifacts/final_run/` |
| `examples/pyqcd/dev6/` | `pyqcd/testing/spectrum/` |
| `examples/pyqcd/dev7/` | `pyqcd/testing/spectrum/` |
| `examples/pyqcd/cmp1/cases_donghx*.py` | `pyqcd/testing/comparisons/donghx/` |
| `examples/pyqcd/cmp1/cases_lqcddb*.py` | `pyqcd/testing/comparisons/lqcddb/` |
| `examples/pyqcd/cmp1/cases_suppl.py` | `pyqcd/testing/comparisons/supplementary/` |
| `examples/pyqcd/cmp1/` 公共代码 | `pyqcd/testing/comparisons/common/` |
| `examples/pyqcd/cmp1/v*` | `pyqcd/testing/comparisons/artifacts/` |
| `examples/pyqcd/cmp1/MAPPING.md` | `pyqcd/testing/comparisons/README.md` |
| `examples/pyqcd/cmp1/cmp1_analysis.*` | `pyqcd/testing/comparisons/docs/comparison_analysis.*` |

## 入口替换

| 旧命令 | 新命令 |
|---|---|
| `python examples/pyqcd/conftest.py` | `python -m pyqcd.testing` |
| `python examples/pyqcd/verify_consistency.py` | `python -m pyqcd.testing.regression.consistency` |
| `python examples/pyqcd/tmd_gradient_flow_demo.py` | `python -m pyqcd.testing.demos.tmd_gradient_flow` |
| `python examples/pyqcd/test9_gluon_tmd_nucleon.py` | `python -m pyqcd.testing.tmd.pdf_workflow` |
| `python examples/pyqcd/test9_verify.py` | `python -m pyqcd.testing.tmd.verify_pdf_workflow` |
| `python examples/test0/main.py` | `python -m pyqcd.testing.regression.distillation.main` |
| `python examples/pyqcd/dev6/main.py` | `python -m pyqcd.testing.spectrum.effective_mass` |
| `python examples/pyqcd/dev7/main.py` | `python -m pyqcd.testing.spectrum.effective_mass_ratio` |
| `python examples/pyqcd/cmp1/main.py` | `python -m pyqcd.testing.comparisons.main` |

历史文档中的旧路径用于标识原始证据。需要重新执行时，以本表新路径为准。
