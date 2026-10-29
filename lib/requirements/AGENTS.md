# AGENTS.md — requirements

功能依赖清单目录，不作为文档资料目录。

- `apt.txt`：由 `bin/apt_install.sh` 逐行读取的 APT 包清单。
- `pip.txt`：由 `bin/pip_install.sh` 通过 `pip install -r` 消费的 Python 包清单。
- 清单一行一个包；`#` 起始行是注释，不是锁文件。修改后至少运行对应安装脚本的 `bash -n`，
  并在目标发行版或虚拟环境中验证包名可解析。
