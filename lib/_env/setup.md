# 环境配置操作

## 三层环境

| 层级 | 文件 | 职责 |
|---|---|---|
| 仓库通用入口 | `env.sh` | PATH、库路径、locale、Git 别名、通用别名 |
| 机器版本快照 | `lib/<name>-vYYYYMMDD>/env.sh` | module、conda、编译器、工具链和机器专属路径 |
| 用户本机覆盖 | `~/env-key.sh`、`~/env.sh` | 密钥、登录令牌和不在仓库中维护的本机参数 |

`~/.bashrc` 和 `~/.zshrc` 当前 source 顺序为：

```text
~/configure/env.sh
~/env-key.sh
~/env.sh
```

后加载文件可以覆盖前面的变量。把机器配置是否覆盖仓库通用值的决定写清楚，不要依赖偶然顺序。

## 通用入口

```bash
source ./env.sh
command -v git
printf '%s\n' "$PATH"
printf '%s\n' "$LD_LIBRARY_PATH"
```

`env.sh` 通过自身位置解析仓库根，适合部署在 `$HOME/configure` 之外。它会避免重复加入仓库 `bin/` 和 `lib/`，但不能阻止机器 `env.sh` 自己重复追加路径。

检查多次 source 是否稳定：

```bash
bash --noprofile --norc -c '
  source ./env.sh
  first_path=$PATH
  source ./env.sh
  test "$first_path" = "$PATH"
  printf "PATH stable\n"
'
```

## 选择版本化配置

先列出可用快照：

```bash
find lib -mindepth 1 -maxdepth 1 -type d -name '*-v[0-9]*' -print | sort
```

查看某个环境的实际动作：

```bash
sed -n '1,240p' lib/<name>-vYYYYMMDD/env.sh
grep -nE '^(module|conda|source|pushd|export|alias|cp|ln) ' lib/<name>-vYYYYMMDD/env.sh
```

确认后，可把机器入口链接或复制到 `~/env.sh`：

```bash
if [ -e ~/env.sh ] || [ -L ~/env.sh ]; then
  mv ~/env.sh ~/env.sh.bak.$(date +%Y%m%d-%H%M%S)
fi
cp lib/<name>-vYYYYMMDD/env.sh ~/env.sh
```

版本化配置通常包含硬编码用户目录、module 名称、conda 环境、网络代理或共享集群路径。不要在没有对应机器和软件栈时直接 source。

如果机器配置需要跟随仓库更新，可使用符号链接；但仓库路径移动或历史目录切换会使链接失效：

```bash
ln -s "$PWD/lib/<name>-vYYYYMMDD/env.sh" ~/env.sh
```

## 新增或更新机器配置

按照仓库约定，更新时新建当天日期目录：

```bash
mkdir -p lib/<name>-v$(date +%Y%m%d)
cp lib/<name>-v<旧日期>/env.sh lib/<name>-v$(date +%Y%m%d)/env.sh
${EDITOR:-vim} lib/<name>-v$(date +%Y%m%d)/env.sh
bash -n lib/<name>-v$(date +%Y%m%d)/env.sh
```

不要直接修改旧日期目录。旧目录用于历史对照、机器回退和差异分析。

## 分节标记

| 标记 | 含义 |
|---|---|
| `@SECTION@` | 激活块 |
| `@@SECTION@@` | 注释掉的备选块 |

常见分节：

```text
@MODULE@
@EXPORT@
@CONDA@
@ENV@
@ALIAS@
@SOURCE@
```

安装或构建命令首次运行后可保留为注释，只保留生效的 export 和环境加载。这样既能复现，也不会在每次 source 时重新安装。

## `lib/set-env.sh`

```bash
source lib/set-env.sh
```

该脚本必须 source，直接执行只影响子进程，当前终端不会获得变量。

当前顺序：

1. Bash 会话 source `~/.bashrc`；Zsh 会话跳过。
2. source `~/.env.sh`。
3. `~/.env.sh` 不存在时，在 `$HOME` 调用 `bin/save-env.sh` 自动生成。
4. source `~/configure/env.sh`。
5. source `~/env.sh`。

三个限制：

1. `set-env.sh` 把配置根硬编码为 `~/configure`，即使脚本位于其他部署目录也不会自动改向。
2. 自动生成的 `~/.env.sh` 会包含大量当前环境变量，可能含 API key、令牌和代理凭据。
3. 被调用的 `save-env.sh` 依赖 Bash 4+ 的 `mapfile` 和 GNU `sort -z`，macOS 默认 Bash 3.2 + BSD `sort` 下无法正常工作。

因此执行前应先检查：

```bash
test -f ~/.env.sh || echo '将自动生成 ~/.env.sh'
umask
bash --version | head -1
sort --version 2>&1 | head -1
```

更安全的做法是手工创建最小 `~/.env.sh`，只包含确实需要恢复的变量。

## 环境快照

```bash
umask 077
bash bin/save-env.sh ~/.env.sh TERM DISPLAY
chmod 600 ~/.env.sh
```

生成后检查文件和值：

```bash
sed -nE 's/^(export )?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' ~/.env.sh 2>/dev/null |
  grep -Ei 'KEY|TOKEN|SECRET|PASSWORD|PASS|PROXY' || true
```

该命令只显示变量名，不打印真实值。发现凭据时应重新生成、删除敏感变量或改用 `~/env-key.sh`。

## 验证

```bash
bash -n env.sh
bash -n lib/set-env.sh
bash -n <版本目录>/env.sh
bash --noprofile --norc -c 'source ./env.sh; command -v git; printf "%s\n" "$LANG"'
```

机器级 module、conda 和编译器只能在对应主机验证。验证时使用子 Shell，避免错误配置污染当前会话。

## 回滚

```bash
ls -l ~/env.sh ~/env-key.sh ~/.env.sh 2>/dev/null
cp ~/env.sh ~/env.sh.bak.$(date +%Y%m%d-%H%M%S)
cp lib/<name>-v<旧日期>/env.sh ~/env.sh
```

恢复后打开新终端或重新 source。密钥文件不进入 Git 回滚流程，应使用受控的本机备份。
