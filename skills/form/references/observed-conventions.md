# 从固定明文快照归纳的格式规则

本文件只归纳 `source-snapshots/` 中固定提交可直接观察到的规则。它用于细化
`naming-and-layout.md`，不覆盖用户明确说明或目标库已批准的特化规则。

## 总则

1. 文件先按职责分层，再按语言命名；同一项目的同类文件必须成体系。
2. 私有性可由文件名、函数名、变量名或私有模块边界表达，但新代码优先采用用户指定的
   显式 `_` 前缀；既有库只依赖私有模块边界时，作为兼容例外保留。
3. 数学符号、量和标准缩写允许保留常规写法，例如 `Nt`、`Pz`、`SU2`、`gamma_5`；
   例外必须服务领域可读性，不能成为随意大小写的借口。
4. 生成文件、上游 vendored 文件和压缩产物保留来源名称与内容；不得为了统一命名破坏
   可重复生成或上游校验。

## C++/CUDA

证据：

- `source-snapshots/pyqcu-dev89/cpp/cuda/qcu/AGENTS.md:5`
- `source-snapshots/pyqcu-dev89/cpp/cuda/qcu/include/clover_dslash.h:14`
- `source-snapshots/pyqcu-dev89/cpp/cuda/qcu/include/lattice_clover_bistabcg.h:11`
- `source-snapshots/pyqcu-dev89/cpp/cuda/qcu/include/define.h:12`

| 对象 | 规则 | 明显示例 |
|---|---|---|
| 根目录 | `include/` 放模板头，`src/` 放 `.cu` 实例化/启动代码，`python/` 放绑定 C API | `cpp/cuda/qcu/{include,src,python}` |
| 头文件 | 全小写下划线，名称映射核心对象或操作 | `clover_dslash.h`、`lattice_wilson_cg.h` |
| 源文件 | 全小写下划线，批量操作用 `apply_<功能>.cu` | `apply_clover_dslash.cu` |
| 对象/类型 | 大驼峰，领域缩写作为一个完整词 | `LatticeCloverBistabCg`、`LatticeWilsonCg` |
| kernel/内部函数 | 全小写下划线，动作在前 | `pick_up_u_x` |
| 宏和编译期常量 | 全大写，两侧 `_` 作为宏锚点；局部槽位可使用短名 | `_BLOCK_SIZE_`、`_SET_PLAN_` |

新增 C++ 对象时，头文件名使用对象含义的小写下划线形式，类型名使用大驼峰；新增源文件
必须能直接对应头文件、模板实例化或明确的操作入口。

## Python

证据：

- `source-snapshots/pyqcd-dev15/pyqcd/AGENTS.md:4`
- `source-snapshots/pyqcd-dev15/pyqcd/lattice/__init__.py:4`
- `source-snapshots/pyqcd-dev15/pyqcd/lattice/_cg.py:27`
- `source-snapshots/pyqcd-dev15/pyqcd/lattice/_cg.py:81`
- `source-snapshots/pyqcd-dev15/pyqcd/analysis/_ana_3dir.py:37`
- `source-snapshots/pyqcd-dev15/pyqcd/contraction/_dynamic.py:668`

| 对象 | 规则 | 明显示例 |
|---|---|---|
| 包/子包 | 全小写，按计算域分域 | `pyqcd/{lattice,analysis,operator,pipeline,testing}` |
| 私有模块 | 复杂库内前缀 `_` | `_gamma.py`、`_disconnected.py` |
| 公共导出 | `__init__.py` 显式 re-export，并用 `__all__` 固定接口 | `lattice/__init__.py` |
| 私有函数 | `_snake_case` | `_two`、`_validate_tseps` |
| 公共函数 | 默认 `snake_case`；领域量开头的接口可保留工程惯用写法 | `cg_coefficient`、`SU2combine` |
| 模块级不可变常量 | 全大写下划线，语义等同编译期/领域常量 | `GAMMA_PROPERTIES`、`RATIO_SCHEMA` |
| 类型 | 大驼峰 | `AnaRatioParams`、`HardwareSpec` |
| 可调用对象 | 既有库允许全小写以模拟函数语义 | `dynamic_contraction` |

公共函数命名补充：用户原规则要求相对独立的接口用小驼峰；Python 科学 API 若已经形成
`domain_symbol + verb` 或标准术语形式，可将该形式登记为库级例外。新接口在无既有兼容约束
时仍先按用户规则选择小驼峰。

## Bash

证据：

- `source-snapshots/configure-main/bin/AGENTS.md:5`
- `source-snapshots/configure-main/bin/agent-dispatch.sh:8`
- `source-snapshots/configure-main/bin/agent.sh:774`
- `source-snapshots/configure-main/bin/conservative.sh:2`

| 对象 | 规则 | 明显示例 |
|---|---|---|
| 用户命令文件 | 全小写；多词命令优先 `-` 连接，工具脚本可使用下划线 | `agent-dispatch.sh`、`save-env.sh` |
| 主/库内脚本 | 全小写，语义分段可用 `_` | `git_init.sh` |
| 测试脚本 | 在目标脚本名后增加 `.test.sh`，保持点划分 | `agent.test.sh`、`save-env.test.sh` |
| 内部函数 | `_snake_case` | `_usage`、`_cleanup` |
| 公共/入口函数 | `snake_case` | `run_claude`、`main` |
| 路径、名称等脚本状态 | `_UPPER_CASE` 或 `_snake_case`，短变量可全大写 | `_SRC`、`_NAME`、`_PATH` |

命令入口必须带 shebang 和可执行位；文件名不得为了统一而破坏用户现有入口或软链接分发。

## Other/静态前端

证据：

- `source-snapshots/lattice-qcd-at-imp.top-stab4/static/js/AGENTS.md:3`
- `source-snapshots/lattice-qcd-at-imp.top-stab4/static/js/theme.js:5`
- `source-snapshots/lattice-qcd-at-imp.top-stab4/static/js/index.js:10`
- `source-snapshots/lattice-qcd-at-imp.top-stab4/static/css/index.css:138`

| 对象 | 规则 | 明显示例 |
|---|---|---|
| JS/CSS 本地文件 | 全小写 | `theme.js`、`papers.js`、`index.css` |
| 全局模块/单例 | 大驼峰，专有缩写保留全大写 | `Theme`、`MusicPlayer`、`I18N` |
| 函数/变量 | 小驼峰 | `applyTheme`、`updateLangToggle`、`displayCount` |
| CSS 类 | 小写 kebab-case | `.navbar-logo`、`.paper-title` |
| vendored/minified | 保留上游名称和内容 | `bulma-slider.min.js`、`fontawesome.all.min.js` |

静态资源的加载顺序属于功能契约；重命名本地模块时必须同步更新入口、事件名和数据引用。
