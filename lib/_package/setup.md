# 包与可执行资源操作

## 系统包清单

`lib/requirements/apt.txt` 与 `lib/requirements/pip.txt` 是功能输入清单，不是锁文件。

### APT

```bash
sed -e 's/#.*//' -e '/^[[:space:]]*$/d' lib/requirements/apt.txt
bash bin/apt_install.sh
```

`apt_install.sh` 实际执行：

```bash
sudo apt install <逐个包名>
```

脚本没有添加 `-y`。`apt` 仍可能询问确认。批量安装前应先运行：

```bash
sudo apt update
apt-cache policy $(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' lib/requirements/apt.txt)
```

清单中的 `openssh` 在部分 Debian/Ubuntu 版本可能需要改为 `openssh-client` 或 `openssh-server`。发行版报“无法定位软件包”时应按实际包名修正清单，不要安装同名无关包。

### Python

系统 Python 直接安装大量包容易污染基础环境。优先创建虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r lib/requirements/pip.txt
```

`bin/pip_install.sh` 直接执行 `pip install -r`，使用当前 `pip` 对应环境。运行前确认：

```bash
command -v python pip
python --version
pip --version
```

清单当前包含重复的 `beautifulsoup4`，包名大小写也不统一。pip 通常按规范化和大小写处理，但清单本身仍应在下一次维护时去重。清单中的 `nodejs` 是 PyPI 包，不一定等同于系统 Node.js；需要 Node.js 时应优先使用发行版、nvm 或官方安装方式。

## Linux 可执行资源

`lib/_package/linux/2048.c` 是单文件终端游戏，不依赖本仓库其他库：

```bash
cc -O2 -Wall -Wextra -o /tmp/2048 lib/_package/linux/2048.c
/tmp/2048
```

编译产物只是临时验证，不应提交。需要长期使用时安装到用户目录：

```bash
install -d "$HOME/.local/bin"
install -m 0755 /tmp/2048 "$HOME/.local/bin/2048"
```

## Windows 可执行资源

`lib/_package/win/` 中的 `.exe` 是二进制分发文件。运行前至少执行：

```powershell
Get-ChildItem .\lib\_package\win\*.exe |
  Get-FileHash -Algorithm SHA256 |
  Format-Table -AutoSize
Get-AuthenticodeSignature .\lib\_package\win\ChineseChess.exe
```

这些文件不应由仓库脚本自动执行。优先在 Windows Defender 或隔离虚拟机中检查；来源和授权不明确时不要运行。

## 验证

```bash
bash -n bin/apt_install.sh
bash -n bin/pip_install.sh
bash -n bin/apt_up.sh
cc -O2 -Wall -Wextra -o /tmp/2048-test lib/_package/linux/2048.c
```

`bin/apt_up.sh` 会执行完整的 `apt update`、`upgrade -y`、`autoremove` 和清理流程，属于系统级变更，不应在仅验证配置时运行。
