# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this directory.

## Overview

This directory contains utility shell scripts (primarily Bash) that are auto-discovered and aliased by `scripts/script_alias.sh` → `tmp/scripts.sh`. Every `.sh` file here becomes a shell alias named after the filename (e.g., `gpush.sh` → `alias gpush.sh='bash /path/to/bin/gpush.sh'`).

Scripts use `.sh` extension even though they are sourced indirectly via aliases (not executed directly). This convention ensures the alias generator can discover them via `find -name "*.sh"`.

## Script Conventions

Every script follows this skeleton:

```bash
#!/usr/bin/env bash
_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
# ... script logic ...
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
```

- `_NAME` and `_PATH` provide self-awareness (needed since scripts are invoked via alias from anywhere).
- Use `${BASH_SOURCE[0]:-$0}` (not bare `$0`) for the script path: it resolves correctly whether the script is **executed** or **sourced**, and never breaks when the calling shell is a login shell (`$0` = `-bash` → `dirname -bash` would error).
- Timestamps bracket every execution for auditability.
- Some scripts add `set -euo pipefail` for strict error handling; older/simpler ones do not.
- Comments are in Chinese and/or English.

## Category Overview

### Git Workflow

| Script | Purpose |
|--------|---------|
| `gpush.sh` | Stage all (`git add -A`), auto-commit with timestamp, push current branch + tags |
| `gpull.sh` | Fetch all remotes, pull with rebase for linear history |
| `gback.sh` | Restore tracked files to HEAD (discard local changes) |
| `dgtag.sh` | Delete all local git tags |
| `gls.sh` | Count lines of git-tracked files (`git ls-files \| xargs cat \| wc -l`) |
| `git_init.sh` | Configure git user, generate ed25519 SSH key, print public key for Gitee/GitHub |

**Cross-repo batch operations** — these push/pull across multiple repositories using relative paths (`${_PATH}/../../repo-name`):
- `zgALLpush.sh` / `zgALLpull.sh` — push/pull configure, lattice-pdf, and PyQCU
- `zgCONFIGUREpush.sh` / `zgCONFIGUREpull.sh` — push/pull this repo only
- `zgLATTICE-PDFpush.sh` / `zgLATTICE-PDFpull.sh` — push/pull `~/lattice-pdf/`
- `zgPYQCUpush.sh` / `zgPYQCUpull.sh` — push/pull `~/PyQCU/`

Push variants use `gpush.sh`; pull variants use `gpull.sh` preceded by `git stash push`.

**Cross-platform** (Gitee mirror): `ggitee.sh` (Linux/macOS) and `ggitee.bat` (Windows).

### HPC / Slurm

Scripts for the Slurm workload manager on CLQCD clusters:

| Script | Purpose |
|--------|---------|
| `ssub.sh` | Submit a job: generates a `.ssub.sh` Slurm script from a template (partition `gpu-debug`, 2 GPUs), then calls `sbatch` |
| `ssqueue.sh` | Watch queue status (`watch squeue -p gpu-debug`) |
| `zsqueue.sh` | Alternative queue viewer |
| `ssrun.sh` | Run interactive job (`srun` with 2 GPUs, 30min timeout) |
| `sstop.sh` | Cancel all jobs for the current user (`scancel --user zhangxin`) |
| `ssnake.sh` | Snakemake workflow helper |
| `ssnsc.sh` | SSH to NSC cluster |
| `ssjtu.sh` | SSH to SJTU cluster |

Default Slurm template (embedded in `ssub.sh`): partition `gpu-debug`, 1 node, 2 tasks, 30 min, 2 GPUs, sources `$HOME/env.sh`. Edit `ssub.sh` directly to change defaults.

### System Management

- **`cpupower.sh`** — CPU governor/frequency control. Uses `case $_NAME` to dispatch: deployed as symlinks `conservative.sh`, `ondemand.sh`, `performance.sh`, `powersave.sh` each pointing to this one file.
- **`swap.sh`** — Re-create swap file (64 GB at `/var/swapfile`).
- **`apt_install.sh`** — Install packages listed in `../docs/apt_requirement.txt`.
- **`pip_install.sh`** — Install packages listed in `../docs/pip_requirement.txt`.
- **`poweroff.sh` / `reboot.sh`** — System power/reboot wrappers.

### Application Launchers

- **`cclaude.sh`** — Launch Claude Code with `--permission-mode auto`.
- **`ddocker.sh`** — Smart Docker container connector: find latest container, auto-start if stopped, detect shell (`zsh`/`bash`/`sh`), exec in with `cd $HOME`. Cross-platform (macOS/Linux).
- **`ccloudmusic.sh`** — Launch NetEase CloudMusic. Works on macOS, native Linux, and WSL (launches Windows executable via `cmd.exe`).
- **`zipython.sh`** — Launch IPython with `clear`.
- **`zjulab.sh`** — Launch Jupyter Lab with `--allow-root`.
- **`vscode_unset.sh`** — Unset VS Code environment variables.

### Initialization / Deployment

- **`sh_init.sh`** — Bootstrap shell environment: back up existing `~/.bashrc`, `~/.zshrc`, `~/.oh-my-zsh`, then deploy from `lib/_bashrc`, `lib/_zshrc`, `lib/_oh-my-zsh`.
- **`vim_init.sh`** — Bootstrap vim: back up `~/.vimrc`, `~/.vim`, deploy from `lib/_vimrc`, `lib/_vim`. Plugins are pre-installed in `lib/_vim/plugged/` (no network needed).
- **`zerotier_init.sh`** — Full ZeroTier VPN setup: install, start service, join network (`48d6023c464e0a5c`), set orbit satellite (`240f181d35`). Supports Linux (systemd/sysvinit/container/WSL) and macOS.

### Utility

- **`wwa.sh`** — `watch` wrapper.
- **`ddu.sh`** — `du -h` wrapper with depth and sorting.
- **`llog.sh`** — Run a command in background, redirect output to `.log.txt`.
- **`zsearch.sh`** — Search file contents (grep) and filenames (find) with color output.
- **`zlog.sh`** — Log viewer.

### Platform-Specific

- **`xxattr.sh`** — Remove macOS Gatekeeper quarantine attributes from common directories. Exits early on non-macOS.
- **`xx99.sh`** — X99 workstation-specific setup.

### Cross-Platform Scripts (.bat / .ps1)

Some scripts have Windows counterparts alongside `.sh` versions:
- `ddocker.bat` / `ddocker.ps1` — Docker connector for Windows
- `cclaude.bat` / `cclaude.ps1` — Claude Code launcher for Windows
- `ccloudmusic.bat` / `ccloudmusic.ps1` — CloudMusic for Windows
- `aaliyundrive.bat`, `bbilibili.bat` — Windows-only app launchers

These are **not** auto-aliased (the alias generator only scans `.sh` files).

### Games

- `ttetris.sh` — Terminal Tetris (by LKJ, 2013)
- `ssnake.sh` — Terminal Snake (by LKJ, 2013)
- `z2048.sh` — Terminal 2048
- `zasciiquarium.sh` — ASCII aquarium animation
- `aaclock.sh` — ASCII art clock

### Other

- **`cctag`** — Binary (not a shell script). Not auto-aliased.
- **`claude_code-skill4git-tag.md`** — Reference document, not a script.

## Adding a New Script

1. Create `bin/your_script.sh` following the skeleton convention above.
2. Run `scripts/script_alias.sh` to regenerate `tmp/scripts.sh` with the new alias.
3. Source `env.sh` (or open a new shell) to pick up the alias.

Scripts that should NOT be aliased: place them elsewhere or use a non-`.sh` extension.
