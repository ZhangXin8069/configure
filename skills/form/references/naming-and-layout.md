# form 命名与目录规则

## 0. 明文参考

本文件给出通用规则；固定提交的逐文件明文位于 `source-snapshots/`。执行复杂或边界命名审计
时，先读 `source-snapshots/README.md` 确认来源、提交和排除项，再读
`observed-conventions.md` 查看从明文归纳出的语言规则。

## 1. 判定轴

每个名称同时处于三条轴上：

1. `[语言]`：`cpp`（编译型，如 C++/CUDA）、`python`（一般解释型）、
   `bash`（特殊解释型）、`other`（其他语言或静态前端等）。
2. `[构件]`：文件、函数、变量、对象、目录或其他领域对象。
3. `[命名法]`：大驼峰、小驼峰、下划线、点划分；`-` 仅作补充关系连接符。

自身本来可以全小写且足够短、含义清楚的名称，不必强制使用复杂命名法。

## 1.1 名称质量与 Git 标签边界

所有命名必须清晰、无歧义，在简短的同时承载最大实际意义。允许使用领域标准缩写，
但缩写不得把名称压缩成需要上下文猜测的标签。

Git 标签文法为 `^(stab|dev|bug|test)[0-9]+(_[0-9]+)*$`。标签名只用于版本定位：

| 场景 | 判定 | 示例 |
|---|---|---|
| 标签列表、版本查询 | 允许 | `git tag --list 'dev*'` |
| 更新、变更、发布或提交说明 | 允许作为版本引用，同时必须说明实际目的 | `follow dev26, 修复解析器边界条件` |
| 代码注释、日志、审计记录 | 允许作为版本证据 | `# dev26 之后改为两阶段提交` |
| 文件或目录名称 | 禁止 | `dev26_parser.py`、`stab15_solver/` |
| 对象、函数、变量、类型、字段 | 禁止 | `Dev26Parser`、`stab15_config` |
| 测试标识、配置键、CLI 命令 | 禁止 | `test9_case`、`bug2_mode` |

判断标准是标签是否承担了名称的业务语义。违规名称必须改成能说明用途的短名称，
并在同一批次修复全部导入、调用点、配置、文档、测试和生成清单。历史日志中的标签引用
属于允许的版本证据，可保留；日志文件名仍不得使用标签名。

## 2. 简单库与复杂库

| 类型 | 判定 | 常见语言 | 默认范例 |
|---|---|---|---|
| 简单库 | 库名全小写，如 `configure`、`lattice-qcd-at-imp.top` | bash、html 等 | `configure` |
| 复杂库 | 库名含大写，如 `PyQCU`、`PyQCD` | C++、Python 等生产语言 | `PyQCU` |

范例用于观察已有结构，明确文字规则优先。用户指定类型时覆盖名称启发式判定。

## 3. 命名矩阵

| 构件 | 默认规则 | 内部标识 | 允许的特殊情形 |
|---|---|---|---|
| include/头文件 | 全小写下划线 | 复杂库内解释型语言文件前缀 `_` | 领域缩写作为完整词且无歧义 |
| src/源文件 | 全小写下划线 | 按语言既有包内约定 | 语言生态强制名称 |
| main/等效入口文件 | 全小写点划分 | 不适用 | 平台强制入口名 |
| 独立公开接口函数 | 小驼峰 | 不适用 | 语言生态强制名称 |
| 其他函数 | 全小写下划线 | 复杂库内解释型语言函数前缀 `_` | 简单动词本身已足够清楚 |
| 宏/编译期常量 | 全大写下划线 | 不适用 | 单位矩阵 `'I'` 等数学符号 |
| 其他变量 | 全小写下划线 | 复杂库内解释型语言变量前缀 `_` | 短小自然词；语义要求保留的缩写 |
| 对象/类型 | 大驼峰 | 复杂库内解释型语言对象前缀 `_` | 短小自然词可全小写 |
| 文档等其他对象 | 使用内容、目的或领域通行名称 | 不适用 | 保留公式、论文或标准中的正式名称 |

示例：

| 名称 | 判定 |
|---|---|
| `conftest.clover.bistabcg.py` | 点划分的入口/测试入口 |
| `pick_up_u_x` | 普通函数，全小写下划线 |
| `applyInitQcu` | 独立公开接口，小驼峰 |
| `gamma_5` | 普通变量，全小写下划线 |
| `_BLOCK_SIZE_` | 宏，全大写下划线 |
| `LatticeCloverBistabCg` | 复杂对象，大驼峰 |
| `agent-custom.json.refer` | 点划分名称，`-` 表达补充关系 |
| `_dict_h5_write` | 复杂库内解释型语言私有函数 |
| `_SetIndexAllocator` | 复杂库内解释型语言私有对象 |

### 3.1 Agent 规则文件命名

所有目录的 agent 指令文件统一使用 `AGENTS.md`。`AGENT.md` 是历史输入错误，不保留为
兼容别名；只存在单数文件时直接重命名为复数。同目录两者并存时，以 `AGENTS.md` 为主文件，
逐项合并 `AGENT.md` 中尚未存在的有效规则并去重，确认无内容丢失后再删除单数文件。
历史日志可以保留旧路径作为既往证据，但现行脚本、配置、测试和文档必须统一引用
`AGENTS.md`。

### 3.2 `logs/` 文件命名

`logs/` 同时承载任务需求单、agent 任务日志、工具日志、用户历史日志和批次索引。
这些对象不能共用一条笼统的文件名规则：

| 类型 | 规则 | 说明 |
|---|---|---|
| 批次索引 | `AGENTS.md` | 仅允许位于 `logs/AGENTS.md`，由 `log` 技能维护；是元数据，不是日志正文 |
| 任务需求单 | `vYYYYMMDD.txt` | 保存用户任务输入或历史需求原文 |
| 阶段日志 | `vYYYYMMDDHHMM.txt` | 阶段成果和阶段报告归档 |
| 一般日志 | `vYYYYMMDDHHMMSS.txt` | 执行中的一般记录 |
| 最终日志 | `vYYYYMMDDHH.txt` | 主任务完成后的全阶段归档 |
| 冲突后缀 | `<时间戳日志>-2.txt`、`-3`、… | 同名冲突时放宽时间戳，不等待锁、不覆盖 |
| 其他日志 | `*.log/*.json/*.tsv/*.csv/*.txt` | 工具日志和用户自定义历史日志；清理前先查引用 |

对应 `strftime` 模式为：阶段 `v%Y%m%d%H%M.txt`、一般 `v%Y%m%d%H%M%S.txt`、
最终 `v%Y%m%d%H.txt`。

agent 日志也允许带连字符的时间格式：

- 阶段：`vYYYY-MM-DD-HH-MM.txt`；
- 一般：`vYYYY-MM-DD-HH-MM-SS.txt`；
- 最终：`vYYYY-MM-DD-HH.txt`。

所有以 `v` 加数字开头的 `logs/*.txt` 必须匹配上述时间粒度或冲突后缀；例如
`v202610161725.txt` 合法，`v20261016bad.txt` 不合法。`logs/AGENTS.md` 是唯一允许的
`.md` 索引文件。agent 日志的具体写入、章节完整性和大小上限由 `log` 技能负责，
form 负责路径、命名和索引位置审计。

## 4. 例外判定

只允许因可观察语义使用例外：

- 大写字母承载数学含义，例如 `'I'` 表示单位矩阵；
- 大写前缀承载路径/环境语义，例如 `_SRC` 表示当前路径；
- 标准化缩写是领域单一词汇，例如 `QCD`、`HDF5`、`CUDA`；
- 小写短词本身无歧义，例如 `hopping`；
- 语言、框架或标准要求固定名称，例如 Python 特殊方法、C++ 运算符重载。

例外必须在目标根 `AGENTS.md` 写明条件，不能只写“允许特殊命名”。

## 5. 文件夹白名单

### 5.1 库根目录

| 名称 | 适用库 | 用途 |
|---|---|---|
| 小写本库名 | 复杂库 | 解释型语言包根 |
| `cpp` | 复杂库 | 编译型语言根 |
| `data` | 所有库 | 本地运行时数据；Git 仅跟踪 `.gitignore`、`AGENTS.md`、`README.md` 契约文件 |
| `docs` | 所有库 | 当前任务文档、附件图片与生成的 `.gitignore` 控制文件 |
| `refer` | 所有库 | 外部参考、书籍、论文、Git 参考库；Git 参考库以 submodule 放在 `refer/git-rep/` |
| `skills` | 所有库 | 本库 agent 技能 |
| `logs` | 所有库 | 任务日志、agent 三态日志、`AGENTS.md` 索引、工具/历史日志与生成的 `.gitignore` |
| `bin` | 简单库 | 可直接调用的工具脚本 |
| `lib` | 简单库 | 版本化配置与基础模板 |
| 特殊功能名称 | 简单库 | 如 `hooks`、`plugins`、`tools`、`static` 等真实功能树 |

白名单之外的顶层目录只有在用户明确批准或本地特化规则登记后才能保留。

`skills/` 是技能的唯一权威源。`.opencode/skills/` 若存在，只作为加载镜像存在，不作为独立业务
目录参与命名和结构审计；镜像内容与软链接目标由目标库的镜像检查入口核验。

### 5.2 库内子目录

允许以下语义类型：

- 子功能名称，如 `solver`；
- 子对象名称，如 `lattice`；
- 子环境名称，如 `cuda`；
- 参考库名称，包括 `refer/books`、`refer/papers`、`refer/git-rep` 及其他 `refer/**`；
- 特殊接口名称，如绑定层 `python`；
- `include`、`src`；
- 文档子目录 `docs`。

子目录命名必须与其父级语言约定一致；正式参考库可以保留上游目录名，但必须在 `refer/` 下
明确标注为外部内容。

### 5.3 参考 Git 子库 (`refer/git-rep/`)

| 对象 | 规则 |
|---|---|
| `refer/git-rep/<name>/` | 必须是 Git submodule（索引模式 `160000`）；`<name>` 保留上游仓库名大小写。新增使用 `git submodule add <url> refer/git-rep/<name>`，禁止整树拷贝或普通 `git clone` 后直接提交。 |
| `.gitmodules` | 每个子库必须有对应的 `path` 和 `url`；URL 是来源凭据，path 必须与 gitlink 一致。 |
| `refer/git-rep/README.md` | 必须存在；逐项记录子库 `path`、来源 URL、用途和致谢。可参考 PyQCD 仓库的清单式写法，但不能缺项或只留仓库名。 |
| `refer/git-rep/docs/` | 本库对参考子库的分析文档，允许 Markdown、TeX、PDF 和图片；上游自带文档留在子库内，不迁移到此处。 |
| 子库工作树 | 只读外部内容；不修改、不提交、不复制上游文件到主库源码或顶层 `docs/`。 |

示例：

```bash
git submodule add https://gitee.com/zhangxin8069/PyQCU.git refer/git-rep/PyQCU
git submodule add https://github.com/IHEP-LQCD/EasyDistillation.git \
  refer/git-rep/EasyDistillation
```

如果 `refer/git-rep/<name>/docs/` 中有本库添加的分析文档，先把文档迁移到
`refer/git-rep/docs/`，再删除旧的普通拷贝并用 submodule 重建。已经正确配置的 submodule
只更新 README 或执行 `git submodule update --init --recursive`，不要无谓删除重建。

## 6. 框架参照

| 语言族 | 参考入口 | 采用重点 |
|---|---|---|
| `cpp` | `PyQCU/cpp/cuda/qcu` | `include`/`src` 分离、按对象和求解器分域、编译入口清楚 |
| `python` | `PyQCD/pyqcd` | 小写包根、模块职责清楚、公开/内部符号边界明确 |
| `bash` | `configure/bin` | 可执行入口集中、短脚本职责单一、直接调用 |
| `other` | `lattice-qcd-at-imp.top/static` | 静态资源按功能域组织，入口与资源边界明确 |

参考框架是结构范例，不是强制复制目录；迁移结构时必须同时保留或更新构建入口。

离线明文目录：

- `source-snapshots/pyqcu-dev89/cpp/cuda/qcu/`
- `source-snapshots/pyqcd-dev15/pyqcd/`
- `source-snapshots/configure-main/bin/`
- `source-snapshots/lattice-qcd-at-imp.top-stab4/static/`

给定范例 URL 已固定为本地明文快照：

| 语言族 | 原始 URL | 本地快照 | 提交 |
|---|---|---|---|
| C++/CUDA | `https://gitee.com/zhangxin8069/PyQCU/tree/dev89/cpp/cuda/qcu` | `source-snapshots/pyqcu-dev89/cpp/cuda/qcu/` | `f73f0b4be6c9bccbd61122b45fa53c2d7c764a74` |
| Python | `https://gitee.com/zhangxin8069/PyQCD/tree/dev15/pyqcd` | `source-snapshots/pyqcd-dev15/pyqcd/` | `811900c76c5b9fb3632ee855a9c2ae97e6df76b6` |
| Bash | `https://gitee.com/zhangxin8069/configure/tree/main/bin` | `source-snapshots/configure-main/bin/` | `ad8623b6355eddd932abe4d1e8be3170321731bc` |
| 其他/静态资源 | `https://gitee.com/zhangxin8069/lattice-qcd-at-imp.top/tree/stab4/static` | `source-snapshots/lattice-qcd-at-imp.top-stab4/static/` | `5ee896da0be245ce3477fa13428fe5c96b1ca760` |

`source-snapshots/` 是固定提交的离线明文证据，不等同于 `refer/git-rep/` 下的可运行参考
子库；前者用于规则核验，后者用于完整参考实现。两者都不替代本库源码。

## 7. 测试命名与归集

- 复杂库默认使用“小写库名/testing”，按功能分组，不能把所有测试堆在单层。
- 简单库可直接在功能目录保留测试；shell 测试常用 `*.test.sh`。
- 成功的测试应合并为可复用功能代码，并附默认值完整的 Python 或 shell 调用脚本。
- 测试调用脚本使用点划分命名，例如 `qcu.solver.smoke.py`；平台强制名称除外。
