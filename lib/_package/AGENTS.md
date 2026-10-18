# AGENTS.md — _package

可执行/打包资源目录（不部署到 `$HOME`，按平台手动取用）：

- `linux/` — Linux 资源（如 `2048.c`）
- `win/` — Windows 可执行程序（ChineseChess/GoChess/Gomoku/SpaceSniffer 等）
- `setup.md` — 包清单安装、编译示例、可执行文件安全边界

二进制文件来源不明或未签名时必须先在隔离环境验证；本目录不会自动运行任何程序。
