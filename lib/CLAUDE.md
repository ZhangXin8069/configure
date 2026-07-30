# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this directory.

## Overview

This directory holds versioned environment configurations and base dotfile templates for deploying ZhangXin's shell environment across heterogeneous machines — personal workstations, laptops, macOS, HPC clusters (Slurm), GPU/NPU compute nodes, Docker containers, and cloud platforms.

## Directory Organization

Two kinds of directories live here:

### Base Templates (`_`-prefixed)

These are **source-of-truth files** deployed to `$HOME` by `bin/sh_init.sh` and `bin/vim_init.sh`:

| Directory | Deployed as | Purpose |
|-----------|------------|---------|
| `_bashrc` | `~/.bashrc` | Bash configuration |
| `_zshrc` | `~/.zshrc` | Zsh configuration (oh-my-zsh, plugins, sources `~/configure/env.sh`) |
| `_vimrc` | `~/.vimrc` | Vim configuration (4-space indent, hybrid line numbers, plugins) |
| `_vim/` | `~/.vim/` | Full vim runtime: plugins (`plugged/`), colors, autoload, UltiSnips, spell |
| `_oh-my-zsh/` | `~/.oh-my-zsh/` | Full oh-my-zsh installation with custom plugins/themes |

**Reference-only** base directories (not deployed to `$HOME`):
- `_docker/setup.md` — Docker development environment guide (pulling images, loading from tar, container setup)
- `_snsc/` — NSC cluster shared configs: `vscode-server-sysroot-env.sh` (VS Code remote server on CentOS 7 with custom glibc), `envs/` (environment module files)
- `_font/` — Font archives (`LinuxFonts.tar.xz`, `WindowsFonts.tar.xz`)
- `_package/` — OS-specific packages: `linux/`, `win/`

When modifying a base template, edit the `_`-prefixed file here, then re-run `sh_init.sh` or `vim_init.sh` to deploy.

### Versioned Environment Configs (`{name}-v{YYYYMMDD}/`)

Each directory represents a **specific runtime environment** with a version date. The core file is `env.sh` — sourced to set up that environment's shell. Some directories also include `setup.sh` (one-time setup commands), `setup.md` (reference docs), additional dotfiles (`_bashrc`, `_zshrc`), or Slurm helper scripts.

**Versioning rule**: when a config needs updating, create a **new directory** with today's date rather than modifying the old one. Old versions are kept as historical reference.

#### Environment Categories

**Personal devices** — single `env.sh` with local paths:
- `computer-v*` — primary workstation
- `laptop-v*` — laptop
- `mac-v*` — macOS (arm64). Includes Homebrew paths, conda, and locally-built tools (htop, btop, watch, tree)
- `phone-v*` — mobile device (Termux)
- `x99-v*` — X99 workstation. Includes `setup.sh` and local `_bashrc`/`_zshrc` overrides
- `usb-v*` — portable USB-stick environment with `setup.sh` and local dotfiles

**GPU compute — AMD DCU** (`dcu-v*`):
- Environment modules (DTK compiler, GCC, OpenMPI, conda)
- CUDA-like toolchain via HIP/DCU
- Includes Slurm helper scripts for job submission (`_salloc.*.sh`, `_sbatch.*.sh`, `_stop.sh`)
- OpenMPI binding script (`openmpi_bind_mlnx.sh`) for Mellanox InfiniBand

**GPU compute — Huawei Ascend NPU** (`npu-v*`):
- CANN toolkit (Ascend Compute Architecture for Neural Networks)
- torch-npu, custom OpenMPI, HDF5, h5py compiled from source
- TileLang for Ascend with custom submodule mirrors on Gitee
- HTTP proxy configuration for git on intranet

**HPC cluster — NSC** (`snsc-v*`):
- Slurm-based cluster at SNSC (Supercomputing Center)
- Environment modules (GCC, CUDA, OpenMPI, Intel oneAPI, CMake, Python)
- Custom `$HOME/sbin`, `$HOME/slib` paths
- Sources PyQCU's `env.sh`
- `snsc-v20260705` is comprehensive: separate env files for conda, crosstool-ng, gperf, help2man, sysroot, texinfo, and vscode-server (with custom glibc/patchelf for CentOS 7 compatibility)

**Docker** (`docker-v*`):
- Container environment setup: `LD_LIBRARY_PATH` for QUDA/QCU, `PYTHONPATH` for PyQCU
- Root-permissive MPI settings (`OMPI_ALLOW_RUN_AS_ROOT=1` + `--allow-run-as-root` alias)
- `python -u` alias for unbuffered output
- Sources `$HOME/env-key.sh` for API keys
- Older versions (`docker-v20241023`, `docker-v20241106`) include local dotfiles and `setup.sh`

**Cloud platforms — Baidu AI Studio** (`aistudio-v*`):
- Free cloud GPU notebooks
- Custom-built htop, OpenMPI, HDF5, h5py from source (no root access)
- `aistudio-v20260407` includes a custom `_bashrc`

**Tools**:
- `claude_code-v*` — Claude Code offline install package: versioned binaries, `cc-switch-cli` and `cc-switch` GUI, download and install scripts. See its `setup.md` for details.
- `zerotier-v*` — ZeroTier VPN setup tutorial (`setup.md`). Comprehensive guide covering service端 (Central web panel) and client setup across Linux/macOS/Windows.

#### env.sh Section Convention

Active configuration uses `@SECTION@` (single `@`); commented-out blocks use `@@SECTION@@` (double `@`):

```
# @MODULE@          — Active: environment module loads
# @@CROSS@          — Disabled: cross-compilation toolchain

# @EXPORT@          — Active: PATH, LD_LIBRARY_PATH, PYTHONPATH exports
# @@MPI@@           — Disabled: alternative MPI configuration block
```

Common sections across env files:
- `@MODULE@` — `module purge / load` calls (HPC environments)
- `@EXPORT@` — environment variable exports
- `@CONDA@` — conda initialization and environment activation
- `@ENV@` — source additional env files (e.g., `env-key.sh` for secrets)
- `@ALIAS@` — shell aliases
- `@SOURCE@` — source other project env scripts (e.g., PyQCU's `env.sh`)

Installation commands (`wget`, `tar`, `./configure`, `make`, `pip install`) are kept as **comments** after first run for reproducibility — only the resulting `export` statements remain active.
