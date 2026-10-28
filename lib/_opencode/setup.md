# OpenCode 安装与配置

## 安装

Linux / macOS：

```bash
bash lib/_opencode/install.sh
bash lib/_opencode/install.sh 2.2.0
bash lib/_opencode/install.sh --new
```

Windows：

```bat
lib\_opencode\install.bat
lib\_opencode\install.bat 2.2.0
lib\_opencode\install.bat --new
```

安装脚本默认版本为 `2.2.0`，默认目录为 `$HOME/.local/bin` 或 `%USERPROFILE%\.local\bin`。可通过 `OPENCODE_INSTALL_DIR` 覆盖目录。

Linux/macOS 的 `OPENCODE_BASE_URL` 可切换二进制源，默认：

```text
https://opencode.ai/files/bin
```

安装脚本会按平台、架构、AVX2 和 musl 选择不同资产。不支持的系统或架构会在下载前失败。

## 版本分支

`config.sh` 通过 `opencode --version` 的主版本决定配置结构：

| 检测结果 | 配置分支 | 文件 |
|---|---|---|
| `0.x`、`1.x` | V1 | `opencode.json` + `tui.json` |
| `2.x` | V2 | `opencode.json` + `cli.json` |

注意：安装脚本默认版本 `2.2.0` 属 V2 分支；`opencode.ai/files/bin` 镜像只提供 2.x 二进制，1.x（如 `1.18.31`）需另行获取。部署后应以实际 `opencode --version` 和 `config.sh --check` 输出为准。

## 配置

先检查：

```bash
opencode --version
bash lib/_opencode/config.sh --check
bash lib/_opencode/config.sh --help
```

macOS 默认 Bash 3.2 执行 `--help` 时，帮助文本中的非 ASCII 标点会让未加花括号的变量名解析失败。应使用 Bash 4+；只读状态检查可使用 `--check`。

默认 dry-run：

```bash
bash lib/_opencode/config.sh \
  --model <provider/model> \
  --small-model <provider/model> \
  --theme dark \
  --lsp on \
  --permission bash=ask \
  --permission edit=ask
```

确认后加 `--apply`。脚本会在覆盖现有文件前创建带时间戳的 `.bak`。

## 插件

```bash
bash lib/_opencode/config.sh --list-plugins
bash lib/_opencode/config.sh --plugin <package>
```

`--plugin` 只把包名写入配置，不执行安装。V1 插件 API 与 V2 不兼容，安装前确认插件明确声明支持目标主版本。

## 认证和密钥

OpenCode 可通过统一启动器注入 provider 与 API key。凭据应放在 `~/env-key.sh` 或系统安全存储，不应写入 `opencode.json`。操作见 [`../_agent/setup.md`](../_agent/setup.md)。

## 回归测试

```bash
bash lib/_opencode/config.test.sh
```

测试使用临时 `XDG_CONFIG_HOME`、隔离的假 `PATH` 和临时目录，覆盖 V2 原生结构、V1 兼容分支与 `--check`。当前测试没有单独设置临时 `HOME`，因此不会隔离用户 `~/.config` 之外的 HOME 级状态。运行需要 `python3`。

## 验证

```bash
bash -n lib/_opencode/install.sh
bash -n lib/_opencode/config.sh
bash -n lib/_opencode/config.test.sh
bash lib/_opencode/config.test.sh
opencode --version
```
