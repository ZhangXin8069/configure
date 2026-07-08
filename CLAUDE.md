# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a personal shell/dotfiles configuration repository by ZhangXin. It manages development environment setup across multiple machines (workstations, laptops, HPC clusters, containers, cloud studios) by providing versioned shell configurations, utility scripts, and environment bootstrapping.

## How It Works

The entry point is `env.sh` — it is **sourced** (never executed) from `.zshrc` or `.bashrc` to set up `PATH`, shell aliases, and environment variables. It:
1. Sources `tmp/scripts.sh` (auto-generated alias definitions)
2. Sources `lib/_git_aliases.sh` (git aliases, shared with bash users)
3. Prepends `bin/` and `~/.local/bin` to `PATH`
4. Defines shell aliases (navigation, grep, etc.)

**Alias generation**: `scripts/script_alias.sh` auto-generates `tmp/scripts.sh` by scanning `bin/` and `tmp/` for `.sh` files and creating a shell alias for each (e.g., `alias gpush.sh='bash /path/to/bin/gpush.sh'`). Run this script whenever scripts are added to `bin/`.

**Initialization**: `bin/sh_init.sh` bootstraps a new machine by backing up existing dotfiles and copying template files (`lib/_bashrc`, `lib/_zshrc`, `lib/_oh-my-zsh`) to `$HOME`.

## Directory Structure and Conventions

| Path | Purpose |
|---|---|
| `env.sh` | Main environment setup (sourced by shells) |
| `bin/` | Utility shell scripts — each becomes an alias automatically |
| `lib/` | Versioned configuration directories |
| `lib/_git_aliases.sh` | Git aliases (sourced by env.sh, shared with bash users) |
| `lib/_bashrc`, `lib/_zshrc`, `lib/_vimrc` | Template dotfiles (copied to `$HOME` by `sh_init.sh`) |
| `lib/_oh-my-zsh/` | Full oh-my-zsh installation with custom plugins/themes |
| `lib/{name}-v{YYYYMMDD}/` | Environment-specific configs with version dates |
| `scripts/` | Initialization and maintenance helpers |
| `docs/` | Reference guides (Jupyter Lab setup, OpenMC installation) |
| `tmp/` | Runtime-generated files (alias scripts, logs) |

### Versioned Config Pattern (`lib/{name}-v{YYYYMMDD}/`)

Each directory represents a specific environment with a version date suffix. When an environment's config needs updating, create a new directory with today's date rather than modifying the old one. Directory names indicate the target:

- `computer`, `laptop`, `mac`, `phone` — personal devices
- `x99` — X99 workstation
- `dcu`, `npu` — GPU/NPU compute nodes
- `docker` — Docker environments
- `snsc` — HPC cluster (Slurm-based)
- `aistudio` — Baidu AI Studio cloud notebooks
- `claude_code` — Claude Code CLI configuration
- `usb` — Portable/USB-stick configurations

Each versioned directory typically contains an `env.sh` with environment-specific variables and setup. These scripts follow a section-marker convention:
- `@SECTION@` (single `@`) — active configuration block
- `@@SECTION@@` (double `@`) — commented-out/optional block (e.g., CUDA, OpenMPI)
- Installation commands are kept as comments after first run for reproducibility; only active exports remain uncommented

The environments serve **scientific computing / lattice QCD research** workflows — compiling and running QUDA, PyQCU, and TileLang across heterogeneous hardware (NVIDIA CUDA, AMD ROCm/DCU, Huawei Ascend NPU) with OpenMPI, HDF5, and cross-compilation toolchains.

## Key Scripts in `bin/`

- **Git helpers**: `gpush.sh`, `gpull.sh`, `gback.sh` (backup branch), `gcomm.sh` (commit with message), `git_init.sh` (init repo with common settings), `gls.sh` (list repos)
- **System**: `apt_install.sh`, `apt_up.sh`, `pip_install.sh` — package installation
- **Power management**: `cpupower.sh` (unified CPU governor control, with `conservative.sh`/`ondemand.sh`/`performance.sh`/`powersave.sh` as symlinks)
- **HPC (Slurm)**: `ssub.sh` (submit job), `ssqueue.sh`/`zsqueue.sh` (queue status), `ssrun.sh` (run interactive), `sstop.sh` (cancel job), `ssnake.sh` (Snakemake workflow helper), `ssnsc.sh` (cluster SSH), `ssjtu.sh` (SJTU cluster)
- **Games**: `ttetris.sh`, `ssnake.sh`, `z2048.sh`, `zasciiquarium.sh`
- **Tools**: `aaclock.sh` (ASCII art clock), `zsearch.sh` (search tool), `llog.sh`/`zlog.sh` (log viewer), `swap.sh` (swap file management)
- **Editors/IDEs**: `vim_init.sh`, `vscode_unset.sh`, `zipython.sh` (launch IPython), `zjulab.sh` (launch Jupyter Lab)
- **Config sync**: `zgALLpull.sh`/`zgALLpush.sh` — pull/push all tracked repos; `zgCONFIGUREpull.sh`/`zgCONFIGUREpush.sh` — this repo only

## Shell and Editor Configuration

- `.zshrc` uses **oh-my-zsh** with the `robbyrussell` theme and plugins: `kubectx`, `aws`, `git`, `you-should-use`, `zsh-syntax-highlighting`, `zsh-autosuggestions`. It sources `~/configure/env.sh` on startup.
- `.bashrc` is a standard Ubuntu-style `.bashrc` with color support, an `ex()` archive extractor, and xhost setup.
- `.vimrc` uses 4-space indentation with expandtab, hybrid line numbers, mouse support, and incremental search with smart case.

## Shell Initialization Order

1. `.zshrc` → sources `~/configure/env.sh`
2. `env.sh` → appends its own sourcing timestamp to `tmp/scripts.sh`, then sources it
3. `tmp/scripts.sh` → auto-generated aliases for all `.sh` files in `bin/` and `tmp/`
4. `env.sh` → prepends `bin/` and `~/.local/bin` to `PATH`, defines additional aliases
