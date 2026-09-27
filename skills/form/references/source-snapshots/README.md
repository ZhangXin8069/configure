# form 明文参考快照

本目录保存 `form` 四个参考 URL 的固定提交明文体，供离线审计和规则校验使用。
快照不跟随远程分支漂移；每个来源同时记录 tag/branch、解析后的提交、逐文件 Git blob
哈希、文件大小和 SHA-256 校验值。

## 快照

| 语言族 | 原始 URL | ref | 提交 | 本地根 | 明文条目 | 符号链接 | 明文字节 | 排除二进制 |
|---|---|---|---:|---|---:|---:|---:|---:|
| cpp/cuda | `https://gitee.com/zhangxin8069/PyQCU/tree/dev89/cpp/cuda/qcu` | annotated tag `dev89` | `f73f0b4be6c9bccbd61122b45fa53c2d7c764a74` | `pyqcu-dev89/` | 70 | 0 | 1,229,465 | 0 |
| python | `https://gitee.com/zhangxin8069/PyQCD/tree/dev15/pyqcd` | annotated tag `dev15` | `811900c76c5b9fb3632ee855a9c2ae97e6df76b6` | `pyqcd-dev15/` | 415 | 0 | 5,430,625 | 365 |
| bash | `https://gitee.com/zhangxin8069/configure/tree/main/bin` | branch `main` | `ad8623b6355eddd932abe4d1e8be3170321731bc` | `configure-main/` | 107 | 15 | 724,206 | 0 |
| other/static | `https://gitee.com/zhangxin8069/lattice-qcd-at-imp.top/tree/stab4/static` | annotated tag `stab4` | `5ee896da0be245ce3477fa13428fe5c96b1ca760` | `lattice-qcd-at-imp.top-stab4/` | 19 | 0 | 1,840,442 | 11 |

tag object 哈希：

| ref | tag object |
|---|---|
| `PyQCU/dev89` | `97eeed783f6b5a8a2f50a6ce9db221c1d0faa751` |
| `PyQCD/dev15` | `592497c5b96232b05c506329f130ddcb30a5028d` |
| `lattice-qcd-at-imp.top/stab4` | `2b0c03639b11dde522d6e79dffa6d8c1d4b58aff` |

## 文件说明

- `<source>/MANIFEST.tsv`：前 6 行为来源元数据，随后一个表头和逐文件记录；字段包含
  远端 mode、Git blob 对象、字节数、原路径和 `included`/`excluded-binary` 状态。
- `<source>/SHA256SUMS.txt`：当前离线普通文件的 SHA-256（不包含该清单自身），可在快照根
  执行 `sha256sum -c SHA256SUMS.txt`；符号链接另见 `SYMLINKS.tsv`。
- `<source>/SYMLINKS.tsv`：保留的符号链接及其目标；当前仅 `configure-main` 有 15 项。
- `<source>/_repository/`：来源仓库根 `LICENSE` 和 `README.md`，用于许可证与项目定位；
  它们不属于 URL 指向的子路径。
- 未复制二进制图片、视频、PDF、图标等；完整路径、对象和大小仍保留在 `MANIFEST.tsv`，
  因此可确认“未复制”与“来源不存在”的区别。

## 使用与刷新

规则审计优先读取 `../observed-conventions.md`，再按主题进入对应快照文件。需要核对原始
上下文时，使用仓库相对路径和 `文件:行号`；不要把当前线上 Gitee 页面当作固定基线。

刷新快照时必须先解析同名 tag/branch，重新生成 `MANIFEST.tsv` 与 `SHA256SUMS.txt`，然后
更新本文件中的 tag object、提交哈希、文件数、字节数和观察规则。若远端已移动或删除，
保留旧快照并在新记录中显式标注，不覆盖历史证据。

## 完整性检查

```bash
cd form/references/source-snapshots/pyqcu-dev89
sha256sum -c SHA256SUMS.txt
```

四个快照均按此命令逐文件校验；`MANIFEST.tsv` 的 Git blob 对象用于与固定提交再次比对。
