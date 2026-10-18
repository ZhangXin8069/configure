# Linux 配置与维护操作

## 操作分层

| 层级 | 常见操作 | 是否需要 root |
|---|---|---|
| 用户环境 | Shell、Vim、字体、SSH、agent | 否 |
| 用户软件 | pip 虚拟环境、`~/.local/bin` 工具 | 否 |
| 系统软件 | APT、Docker、ZeroTier、CPU 调频、Swap | 通常需要 |
| 破坏性维护 | 重启、关机、升级、删除更新缓存 | 需要且应单独确认 |

## 安装顺序

```bash
cd ~/configure
bash bin/sh_init.sh -a
bash bin/vim_init.sh
source env.sh
```

然后按需要执行：

| 场景 | 文档 |
|---|---|
| 系统软件和 Python 包 | [`../_package/setup.md`](../_package/setup.md) |
| SSH 密钥 | [`../_ssh/setup.md`](../_ssh/setup.md) |
| Docker | [`../_docker/setup.md`](../_docker/setup.md) |
| ZeroTier | [`../_zerotier/setup.md`](../_zerotier/setup.md) |
| 字体 | [`../_font/setup.md`](../_font/setup.md) |
| 旧 glibc 上的 VS Code | [`../_snsc/setup.md`](../_snsc/setup.md) |

## Swap

`bin/swap.sh` 会执行：

```text
sudo swapoff -a
sudo dd if=/dev/zero of=/var/swapfile bs=1M count=65536
sudo mkswap /var/swapfile
sudo swapon /var/swapfile
```

它会先关闭所有 Swap，再创建 64 GiB `/var/swapfile`。该脚本不会把 Swap 写入 `/etc/fstab`，因此重启后不保证自动启用。

执行顺序存在失败窗口：脚本先运行 `swapoff -a`，之后 `dd`、`mkswap` 或 `swapon` 任一步失败时不会自动恢复原 Swap，而且脚本没有 `set -e`。生产机器上应先确认已有 Swap 条目和 fstab：

```bash
swapon --show
cat /etc/fstab
```

失败后的恢复方式取决于原 Swap 类型。若 fstab 仍保有原条目，可尝试 `sudo swapon -a`；若原 Swap 是临时文件，需要手工执行 `mkswap` 和 `swapon <路径>`。不要在未确认设备路径时自动重建。

执行前检查空间和现有 Swap：

```bash
swapon --show
free -h
df -h /var
```

低内存工作站创建 64 GiB Swap 可能占用大量磁盘。需要永久配置时应手工审核 `/etc/fstab`，不要重复执行脚本。

## CPU 调频

`bin/cpupower.sh` 根据调用名分发四种策略：

| 调用名 | 策略 | 额外设置 |
|---|---|---|
| `conservative.sh` | conservative，1.4 到 4.5 GHz | 保留部分 C-state |
| `ondemand.sh` | ondemand，1.4 到 3.4 GHz | 保留部分 C-state |
| `performance.sh` | performance | 禁用多数空闲状态 |
| `powersave.sh` | powersave | 保留 C-state 3 |

运行前检查：

```bash
command -v cpupower
cpupower frequency-info
cpupower idle-info
```

这些范围来自特定机器，其他 CPU 不应直接使用。脚本依赖对应名称的符号链接或复制入口。

## 电源操作

```bash
bin/poweroff.sh
bin/reboot.sh
```

两者分别执行 `sudo shutdown -h now` 与 `sudo reboot`，会立即中断所有本地任务。不要在自动化验证或未保存工作时运行。

## 发行版兼容

`bin/apt_install.sh` 和 `bin/apt_up.sh` 只适用于 APT 系统。Fedora、RHEL、Arch、openSUSE 和 Alpine 应使用各自包管理器。

部分文件工具依赖 GNU 参数：

```text
find -printf
stat -c
du -d
```

这些工具在 macOS/BSD 上通常不可用或语义不同。Linux 使用前也应确认对应工具版本。

## 验证

```bash
bash -n bin/swap.sh
bash -n bin/cpupower.sh
bash -n bin/poweroff.sh
bash -n bin/reboot.sh
uname -a
cat /etc/os-release
```

只做语法和只读环境检查，不执行 Swap、调频、重启或关机来“验证配置”。
