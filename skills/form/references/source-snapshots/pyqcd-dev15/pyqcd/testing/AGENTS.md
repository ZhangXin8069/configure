# AGENTS.md — pyqcd/testing

`pyqcd/testing` 统一承载契约测试、回归测试、可执行示例、参考基线及历史验证产物。
生产模块不得反向导入本目录。

## 目录约定

| 路径 | 内容 |
|---|---|
| `__init__.py`, `conftest.py`, `__main__.py` | 中心测试登记与执行入口 |
| `demos/` | 自包含可运行示例 |
| `regression/` | 蒸馏、GEVP、冻结基线一致性回归 |
| `tmd/` | 梯度流胶子 TMD-PDF 工作流与运行快照 |
| `spectrum/` | 有效质量、谱学与 ratio 工作流 |
| `comparisons/` | 外部参考对照，按 `donghx`、`lqcddb` 来源分类 |

- 可执行代码按功能命名，不保留 `devN`、`testN`、`cmpN` 等历史 tag 目录名。
- 运行快照置于对应 `artifacts/`，只保留时间戳或 `initial_run`、`extended_run`、
  `final_run` 等语义名。
- 冻结基线代码不得改写其物理结论；适配层与新增测试放入包内相应功能目录。

## 运行

```bash
python -m pyqcd.testing
python -m pyqcd.testing.tmd.pdf_workflow --dry-run
python -m pyqcd.testing.regression.distillation.main --help
python -m pyqcd.testing.comparisons.main --help
```

完整迁移映射见 `MIGRATION.md`。
