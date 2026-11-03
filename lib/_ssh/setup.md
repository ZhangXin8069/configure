# SSH 配置操作

## 目标

建立可验证的 SSH 密钥认证、持久化或可重复加载的 ssh-agent、清晰的 `~/.ssh/config` 主机别名，并正确使用仓库内网与集群快捷脚本。

## 安全边界

1. 私钥只保存在本机 `~/.ssh/`，禁止复制进仓库或聊天记录。
2. 不推荐 `StrictHostKeyChecking=no`，它会绕过主机身份校验。
3. `ssh-keyscan` 只能读取公钥，不能证明目标身份；首次连接应通过可信渠道核对指纹。
4. 多身份场景使用不同密钥，并通过 `IdentitiesOnly yes` 限制候选密钥。
5. `~/.ssh/config` 建议权限 `600`，`~/.ssh` 建议权限 `700`。

## 检查和生成密钥

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh

ls -l ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub 2>/dev/null || true
```

仅在不存在时生成：

```bash
test -f ~/.ssh/id_ed25519 || \
  ssh-keygen -t ed25519 -a 64 -C "zhangxin8069@qq.com" -f ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

`bin/git_init.sh` 也会生成同名密钥，但它不是幂等脚本。已有密钥时不要重复运行。

查看公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

将公钥加入代码托管平台：

| 平台 | 地址 |
|---|---|
| GitHub | `https://github.com/settings/keys` |
| Gitee | `https://gitlab.itp.ac.cn/profile/sshkeys` |

## 加载 ssh-agent

Linux 或通用 Unix：

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
ssh-add -l
```

macOS 可将密钥写入 Keychain：

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
ssh-add -l
```

`bin/git_init.sh` 启动的 agent 只对当前 Shell 有效。新终端需要重新加载，或由桌面环境、systemd 用户服务或 Keychain 统一管理。

## 主机别名

可选示例，写入 `~/.ssh/config`：

```sshconfig
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  ServerAliveInterval 30
  ServerAliveCountMax 3

Host gitlab.itp.ac.cn
  HostName gitlab.itp.ac.cn
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
```

通过跳板机访问时可增加：

```sshconfig
Host internal-host
  HostName 10.0.0.20
  User zhangxin
  ProxyJump bastion
```

展开后的最终配置可只读检查：

```bash
ssh -G github.com | grep -E '^(hostname|user|identityfile|identitiesonly) '
ssh -G internal-host | grep -E '^(hostname|user|proxyjump) '
```

## 主机指纹

首次连接时核对提示中的 SHA256 指纹。已有可信指纹时由 OpenSSH 自动比对。需要排查 `known_hosts` 时先看懂错误，再只删除对应主机条目：

```bash
ssh-keygen -F github.com
ssh-keygen -R github.com
```

错误示例：

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

出现该警告时先确认服务器是否轮换密钥，不要直接清空整个 `known_hosts`。

## 验证托管平台

```bash
ssh -T git@github.com
ssh -T git@gitlab.itp.ac.cn
```

部分平台认证成功时仍返回非零退出码，应以输出中是否包含成功身份或仓库权限提示为准。

## 仓库快捷入口

### 局域网 `ss`

`bin/ss.sh` 和无后缀符号链接 `bin/ss` 连接 `192.168.188.<末位>`。

| 参数 | 用户 | 默认末位 |
|---|---|---|
| 无参数、`k`、`19` | `kfutfd` | `19` |
| `20` | `kfutfd` | `20` |
| `z`、`3` | `zhang` | `3` |
| `x`、`4` | `xin` | `4` |
| `zx`、`2` | `zhangxin` | `2` |
| `y`、`11` | `yang` | `11` |
| `ht`、`12` | `haotian` | `12` |
| `yht`、`yh`、`13` | `yanghaotian` | `13` |

示例：

```bash
ss
ss x
ss zx42
ss 20
ss 42
```

纯数字参数按“已登记数字映射 > 最低优先级默认用户”解析：例如 `ss 20` 使用 `kfutfd`，
`ss 42` 未命中已登记映射时使用 `zhangxin`，最终执行
`ssh 192.168.188.42 -l zhangxin`。脚本只接受一个参数，IPv4 末位范围为 `1..254`。

### 固定主机

| 命令 | 目标 |
|---|---|
| `ssnsc.sh` | `zhangxin@222.200.137.16:10023` |
| `ssjtu.sh` | `weiwang@bl-0.inpac.sjtu.edu.cn:22` |
| `xx99.sh` | `kfutfd@172.25.193.104:22`，随后运行 `ddocker.bat` |

`xx99.sh` 支持：

```bash
SSH_USER=<用户> SSH_PORT=<端口> xx99.sh
xx99.sh -n
```

`-n` 跳过远程 `ddocker.bat`，直接进入 X99 终端。默认模式要求 ZeroTier 在线和远端可执行 `ddocker.bat`。

这些脚本包含个人网络与主机信息，只适合当前部署环境。其他机器应修改仓库源文件或使用独立 `~/.ssh/config`，不要通过关闭主机校验来适配。

仓库内所有交互式 SSH 快捷入口统一传入 `ServerAliveInterval=30` 与
`ServerAliveCountMax=3`。客户端每 30 秒发送一次加密保活探测，连续 3 次无响应才判定失联；
这主要用于避免空闲连接被 NAT、防火墙或服务端的无流量超时提前回收。

## SSH 后远端 screen

仓库内 8 个交互式 SSH 入口不再在本地 SSH 前创建 screen，而是直接执行带 TTY 的 SSH。
认证成功后在远端检查 `screen`，并创建新的 UTF-8 会话：`-S` 与窗口标题 `-t` 都使用本地
SSH 客户端主机名，`SSH_SCREEN_NAME` 可显式覆盖。命令不使用 `-r`、`-R` 或 `-d -R`，
因此不会自动进入旧会话；同一客户端可以并行建立多个 SSH，每个连接获得独立的远端 screen。
窗口 term 优先使用 `screen-256color`，远端缺少该 terminfo 时回退 `screen`。

远端脚本类型由 `SSH_REMOTE_SHELL=posix|powershell` 控制。默认 19 号 Windows 主机和 X99
使用 PowerShell，其余入口使用 POSIX `sh`；可在调用前显式覆盖。PowerShell 分支只使用
PowerShell 原生命令检测 screen，不发送 `if command`、`&&`、`>&2` 或 `exec` 等 POSIX 语法。

`xx99.sh` 的 ddocker 等既有远端命令也会按 PowerShell 语法执行。所有远端没有 screen 时都只输出
warning 并进入交互 shell，不再依赖本地 `_screen-guide.txt` 或本地是否安装 screen。

本地 `scn` 新建会话仍使用 `-U -T screen-256color`（terminfo 缺失时回退基础 `screen`），
`scr` 重连本地旧会话前会在线发送 `encoding utf8`。加载 `env.sh` 或启动 agent 时仍会把旧
本地窗口继承的 `TERM=screen/dumb` 归一化，避免 cl/op/co 页面乱码。

重新加载环境后可直接使用：

```bash
source ~/configure/env.sh
scn [名字]       # 新建；名字默认取 SSH_CLIENT 的客户端地址
scl              # 查看
scr [名字]       # 重连并踢掉旧连接
scw              # 清理失效的 screen socket
```

新建 session 后按 `Ctrl+a d` 脱离。上述 `scn/scl/scr/scw` 管理的是本地会话；SSH 入口管理的是
登录成功后的远端会话，两者相互独立。

## 排障顺序

```bash
ssh -V
ssh-add -l
ssh -vvv <host>
ssh -G <host>
```

1. 确认 DNS 与端口可达。
2. 确认目标用户和端口。
3. 确认 agent 已加载正确密钥。
4. 检查服务端 `authorized_keys` 权限。
5. 最后才增加 `-vvv`，并妥善处理日志中的用户名、主机名和路径信息。
