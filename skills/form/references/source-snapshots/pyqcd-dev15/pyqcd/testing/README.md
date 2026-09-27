# PyQCD testing

本目录是 `examples/` 迁移后的唯一归属，集中提供：

1. 中心集成测试入口 `python -m pyqcd.testing`；
2. 可独立运行的示例与回归工作流；
3. 冻结参考基线和历史运行产物；
4. 按来源隔离的 donghx/lqcddb 对照测试。

## 分类

| 分类 | 路径 | 说明 |
|---|---|---|
| 示例 | `demos/` | 不依赖历史 tag 命名的可运行演示 |
| 回归 | `regression/` | 蒸馏管线、GEVP、基线一致性 |
| TMD | `tmd/` | 梯度流胶子 TMD-PDF 全链及快照 |
| 谱学 | `spectrum/` | 有效质量、能量和 ratio 工作流 |
| 对照 | `comparisons/` | 外部参考对照与证据 |

对照套件按来源拆分为 `comparisons/donghx/`、`comparisons/lqcddb/` 和
`comparisons/supplementary/`。公共硬件、数据与参考桥位于
`comparisons/common/`，不得把外部参考实现作为生产包依赖。

## 标准入口

```bash
python -m pyqcd.testing
python -m pyqcd.testing.demos.tmd_gradient_flow
python -m pyqcd.testing.tmd.pdf_workflow --dry-run --smoke
python -m pyqcd.testing.regression.consistency
python -m pyqcd.testing.regression.distillation.main --help
python -m pyqcd.testing.spectrum.effective_mass --help
python -m pyqcd.testing.spectrum.effective_mass_ratio --help
python -m pyqcd.testing.comparisons.main --help
```

历史 tag 只出现在冻结证据文本和 `MIGRATION.md` 的旧路径列中。新代码目录不保留
`dev6`、`dev7`、`test9_1`、`test9_2`、`cmp1` 等命名。
