# AGENTS.md — screen 技能

本目录为实现 `screen` 技能的 `SKILL.md`（接管 screen 会话、以 `<pid>.<名称>` 作为默认会话环境、注入命令并用 hardcopy/log 回读）。SKILL.md 为唯一权威内容，勿复制改动。
每次注入前过三道闸门（`Attached` / 画面 ≥2s 静态 / 末行为提示符）；静态阻塞默认用 `q`/`Ctrl-C` 清除，编辑器、可能丢数据或清除失败先请示；画面自行变化（有人在输入）只读。
远程会话（前台为 ssh）保活是硬性要求：登记后必须后台启动 `scripts/screen-keepalive.sh`（间隔 <30s、无必要指令注入 `ls`，受锁与闸门约束），收尾用 stopfile 停止；多代理共用同一会话必须 `flock` 串行化且闸门在锁内，脚本路径不依赖 `$COMMANDCODE_SCRATCHPAD` 等会话变量。
远程目录与本地对应目录只在**工作集**内要求一致；工作集偏差时按 `bin/sh_init.sh` 约定备份远程（`mv <path> <path>.<时间戳>.bak`）后以本地为准写入并复算指纹；读取/检索走本地、执行与结果以远程为准，禁止 scp/rsync。
不自动 `quit`/`kill`、不改会话名、不改写用户文件、不新建 SSH/SCP/SFTP/nc 通道、不代输密码或处理 2FA；`configure` 默认解析为本机配置库，远端同名目录以本地为准。
抓屏与日志放 `$COMMANDCODE_SCRATCHPAD`；有 Git 改动时按上级 `AGENTS.md` 公共契约执行 `git diff --check`，未经明确要求不自动暂存、提交或推送。
