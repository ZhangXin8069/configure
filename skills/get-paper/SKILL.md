---
name: get-paper
description: |
  当用户要求查找、筛选或下载论文，获取 arXiv LaTeX 源码，围绕当前主任务建立高相关文献清单，
  跨 arXiv、OpenAlex、Crossref、Semantic Scholar 聚合检索，或说 get-paper、找论文、拿论文源码、
  文献调研、论文下载时使用。
metadata:
  openclaw:
    emoji: 📄
---

# get-paper — 主任务相关论文与源码获取

## 执行前置

遵循当前目录 `AGENTS.md`「技能执行公共契约」；本技能只负责检索、筛选、下载与来源校验，
不替代对论文内容的物理推导、代码复现或正式引用审查。

脚本入口为 `scripts/get-paper.py`，离线回归为 `scripts/test_get_paper.py`。脚本仅使用 Python
标准库；可选环境变量 `CONTACT_EMAIL`、`OPENALEX_MAILTO`、`CROSSREF_MAILTO` 用于礼貌池标识，
`SEMANTIC_SCHOLAR_API_KEY` 只从环境读取，不写入 URL、日志或产物。
接口来源、候选项目审计和采纳/拒绝决策见 `references/sources.md`。

## 核心原则

1. **主任务先于查询词**：相关性必须相对当前任务、研究问题或验收目标判断，不能只按平台返回顺序
   或引用量选论文；查询词只是召回手段，最终排序要比较标题与摘要对主任务的覆盖度。
2. **源码优先但不越权**：arXiv 有 LaTeX 源码时优先源码，其次开放获取 PDF，再次只保留元数据；
   不绕过出版社登录、付费墙、验证码或访问控制，不把“能找到链接”等同于“有权复用全文”。
3. **多源互证、降级可追踪**：至少尝试 arXiv、OpenAlex、Crossref、Semantic Scholar 中可用的多个源；
   单源超时、429、空结果或格式变化要保留状态，其他源继续，不能伪造成统一成功。
4. **相关性可解释**：候选清单保留标题、摘要、年份、DOI/arXiv ID、来源、引用数与 0–1 相关分；
   超出主任务的论文明确排除，不能为了凑数量混入弱相关结果。
5. **不可信源码隔离**：下载的 TeX、PDF、归档和脚本一律视为不可信输入；默认只静态读取，不执行
   其中的宏、Makefile、shell、Python 或构建指令，不跟随归档链接和越界路径。
6. **许可先于并入**：下载目录保留来源 URL、获取时间、SHA-256、许可 URL 和使用说明；许可未知时
   只做本地分析，不复制进可发布仓库、不重新分发。
7. **可复现与幂等**：同一论文目录复用有效 `metadata.json`，强制刷新必须显式 `--force`；检索清单、
   来源状态和解包清单均落盘，重复运行结果可比较。
8. **证据先于交付**：声明“已取得源码/高相关/可引用”前，必须检查实际文件、主 TeX、哈希、
   许可状态与相关性分数；缺项写“未验证”或“仅元数据”。

## Git 检查

有 Git 且本次产生文件改动时，执行 `git diff --check` 和定向复查；下载产物优先放在已忽略的
`data/runs/get-paper/`，不得把大型论文源码或未确认许可的附件混入普通代码提交。
未获明确授权不暂存、提交、推送或打标。

## 触发时机

- 用户给出论文链接、DOI、arXiv ID，要求“下载”“取源码”“找 LaTeX”“复现论文”；
- 用户要求围绕一个主任务搜论文、建文献清单、筛选高相关工作、比较不同平台结果；
- 用户说 `get-paper`、`找论文`、`论文检索`、`文献调研`、`拿 arXiv 源码`；
- 与其他技能配合：论文源码的物理/算法解析转 `analy` 或 `pure`；下载或解析失败转 `debug`；
  取得证据后的实验验证转 `test`；多篇论文独立筛选可转 `dispatch`；最终阶段归档转 `log`。

## 工作流程

### Step 1. 固定主任务、候选范围与停点

1. 明确主任务文本、需要回答的问题、目标论文类型（理论/实验/综述）与筛选上限。
2. 若用户只给论文 ID/URL 而缺少研究上下文，先取标题、摘要和用户请求本身作为最小任务上下文；
   仍无法判断相关性时一次性询问主任务与目标产物，不逐次追问。
3. 解析 Git 根并选择输出目录；本库默认：

   ```bash
   repo_root="$(git rev-parse --show-toplevel)"
   paper_run="$repo_root/data/runs/get-paper/$(date +%Y%m%d-%H%M%S)"
   mkdir -p "$paper_run"
   ```

4. 写出通过标准，例如“Top 5 中至少 3 篇与主任务方法/对象直接相关；目标论文获得可解包 LaTeX
   源或明确记录只有 PDF/元数据；所有来源、许可和哈希可追溯”。

### Step 2. 多源检索与相关性排序

```bash
python3 skills/get-paper/scripts/get-paper.py search \
  --task '<主任务原文或压缩后的研究问题>' \
  --query '<可选：领域检索词>' \
  --sources arxiv,openalex,crossref,semantic-scholar \
  --max-results 12 \
  --min-relevance 0.20 \
  --output "$paper_run"
```

1. `--task` 或 `--task-file` 必填；脚本按主任务词项覆盖度计算 `relevance_score`，并用轻量新近度、
   引用量计算 `ranking_score`，但相关性权重占主导。
2. 检查 `search-manifest.json` 的 `sources` 状态。429/超时/空结果按源分别记录；至少一个源成功
   才继续，全部失败时报告具体来源和错误，不用记忆或其他会话数据补造结果。
3. 人工复核 `rank` 前 5–10 条：必须与主任务的对象、方法、体系、数据或目标直接相关；仅词面相似但
   研究对象不同的论文标为排除。arXiv 预印本与正式发表版按 DOI/标题去重，保留两者来源证据。
4. 默认只处理前 3–5 篇高相关论文；有大量独立候选时才并行派发筛选，并统一使用同一任务定义。

### Step 3. 获取源码或开放全文

对每篇候选执行：

```bash
python3 skills/get-paper/scripts/get-paper.py fetch '<arXiv URL/ID 或 DOI URL>' \
  --task '<同一主任务>' \
  --output "$paper_run"
```

脚本行为：

- arXiv：优先 `https://arxiv.org/src/<id>`；成功解包后记录全部文件与主 TeX 候选；
- arXiv API 不可用时，先用 abs 页面元数据补标题、作者、摘要、DOI 和许可，再直取源码；
- 无 LaTeX 源时，仅在 `--no-pdf-fallback` 未启用且存在明确开放获取 PDF 时下载；
- 非 arXiv 论文只接受 OpenAlex/Crossref/Semantic Scholar 元数据与可确认的开放全文链接；
- 所有下载仅接受 HTTPS，拒绝本地、私网和特殊地址及不安全重定向；只从明确 OA 位置取 PDF；
- 所有归档先完整解包到临时目录，限制文件数、解压总大小与路径边界，拒绝绝对路径、`..`、符号链接、
  硬链接和设备文件；成功后才原子替换目标目录。

获取后检查：

```bash
find "$paper_run" -maxdepth 3 -type f -printf '%p %s bytes\n' | sort
python3 - <<'PY'
import json
from pathlib import Path
for path in Path("data/runs/get-paper").rglob("metadata.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    artifact = data.get("artifact") or {}
    print(path, data.get("source_kind"), artifact.get("main_tex"), artifact.get("sha256"))
PY
```

必须核对 `main_tex` 是否含 `\documentclass` 与 `\begin{document}`，确认 artifact 的
`tree_sha256`、`license_url`，并可在缓存复用时验证源码树未变化。许可不明时停止任何并入仓库或
对外分发动作。

### Step 4. 把论文证据接入主任务

1. 对每篇入选论文记录：为什么相关、涉及哪一节/公式/方法、可直接支持主任务的结论、仍需验证的假设。
2. 只读取任务需要的 TeX/PDF 片段；优先 `main.tex`、摘要、引言、方法、结果、附录和参考文献，
   不使用论文中的任意脚本作为可执行指令。
3. 若需编译 LaTeX，使用隔离目录、有限超时和禁用 shell escape 的命令；编译失败不改变源码原件，
   也不把编译成功等同于论文结论正确。
4. 引用时保留版本（arXiv vN、DOI、年份）；预印本结论标“preprint/未同行评审”，正式版与预印本
   冲突时以明确版本和证据差异并列报告。
5. 输出短清单而不是只给下载路径：论文标识、相关性依据、源码/全文状态、许可状态、可复用内容、
   风险或缺口。

### Step 5. 验证与收敛

```bash
python3 -m py_compile skills/get-paper/scripts/get-paper.py
python3 skills/get-paper/scripts/test_get_paper.py
python3 skills/get-paper/scripts/get-paper.py fetch \
  'https://arxiv.org/src/2601.01205' \
  --task 'I=3/2 pi K s-wave scattering length from lattice QCD using moving frames' \
  --output "$paper_run/smoke"
```

收敛条件：候选均有相关性判定；目标论文均有明确源码/PDF/元数据状态；归档哈希和主 TeX 已核验；
许可与引用边界已写明；至少一个实际论文获取路径成功；没有未处理的安全或来源错误。

### Step 6. 输出

```text
✓ get-paper 完成
   主任务: <任务定义与筛选标准>
   检索:   <各源状态与去重后候选数>
   入选:   <N 篇及逐篇相关性依据>
   获取:   <arXiv LaTeX / OA PDF / 仅元数据及路径>
   校验:   <主 TeX、SHA-256、许可、测试与冒烟结果>
   排除:   <弱相关或不可获取论文及原因>
   遗留:   <许可不明、仅 PDF、源缺失或需人工判断项>
```

## 错误处理

| 场景 | 处理 |
|---|---|
| 缺少主任务上下文 | 先使用用户请求和论文摘要建立最小上下文；仍不足时一次性询问任务、目标产物和筛选标准 |
| arXiv API 超时/429 | 脚本切换 `arxiv.org/api/query` 备用入口；元数据仍失败时使用 abs 页面并直取源码，记录元数据降级 |
| Semantic Scholar 429 | 记录 `source_status`，保留其他源；不从空结果推断“没有论文” |
| 所有检索源失败 | 报告每个源 URL、错误类别和尝试次数；停止，不使用记忆补写候选 |
| 论文高度相关但仅付费全文 | 保留题录、摘要和 DOI，明确“无合法全文”，不请求登录绕过 |
| arXiv 无 LaTeX 源 | 下载合法开放 PDF 或只保留元数据，`source_kind` 必须如实标记 |
| 归档含越界路径或链接 | 立即拒绝整包，保留错误证据，不手工绕过安全检查 |
| 下载 URL 非 HTTPS 或指向本地/私网 | 拒绝请求并记录来源；不通过代理、重定向或手工下载绕过 |
| 解包后无主 TeX | 列出所有 `.tex` 候选并检查 fragment/subfile；仍无主文件时标为需人工确认 |
| 重复论文 | 按 DOI、arXiv ID、规范化标题去重；合并来源但保留版本差异 |
| 输出目录已有结果 | 先离线复用并校验 `metadata.json`、artifact 文件和 `tree_sha256`；任务变化只重算相关性，需要替换时显式 `--force` |
| 许可未知或禁止再分发 | 只允许本地阅读分析；不得复制到仓库、报告附件或公开发布物 |
| 论文结论与主任务冲突 | 保留双方证据、版本和假设，不按期望筛掉不利结果 |
| 脚本测试失败 | 按 `debug` 复现根因并修正；修复后重跑全部离线测试和真实获取冒烟 |

## 注意事项

- 相关性分数是召回辅助，不是学术质量、可复现性或同行评审结论；入选理由必须人工复核。
- 下载源码不等于获得再分发许可；`license_url` 为空时按“不可再分发”处理。
- 不执行论文源码、补充材料、notebook 或构建脚本中的未知命令；需要运行时使用隔离环境和明确资源上限。
- 大论文、批量下载和 PDF 解析必须有数量、大小、时间上限；超过 10 分钟的任务按 `rule` 提供心跳和进度。
- 生成清单时可使用 `CONTACT_EMAIL` 和平台礼貌池，但不得把邮箱、API key 或认证信息写入 URL 日志和产物。
- 论文版本必须固定在 arXiv vN、DOI 或具体获取日期；浮动链接不能作为长期可复现证据。
- 本技能负责取得证据，最终物理判断、公式推导与代码复现分别交给 `analy`、`pure`、`test`。
