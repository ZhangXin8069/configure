# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this directory.

## Overview

Reference documents, package requirement lists, and image assets. These files are consumed by scripts in `bin/` or serve as standalone guides.

## Package Requirement Lists

- **`apt_requirement.txt`** — APT packages. Consumed by `bin/apt_install.sh` (runs `sudo apt install $(cat docs/apt_requirement.txt)`). Edit this file to add/remove system packages; re-run `apt_install.sh` to apply.
- **`pip_requirement.txt`** — Python packages (PyTorch, NumPy, SciPy, Matplotlib, Jupyter, mpi4py, Cython, etc.). Consumed by `bin/pip_install.sh`. Commented-out packages (prefixed with `#`) are excluded from installation.

Both files are dependency manifests, not "install once" scripts — they list the target state. Keep them in sync with what's actually needed.

## Setup Guides

- **`julab_settings.md`** — Jupyter Lab configuration guide. Covers: extension installation (Chinese language pack, GitHub, LaTeX, drawio, LSP, variable inspector, execution time, system monitor, magic commands), Cling C++ kernel setup, and remote connection setup. Written as personal notes with pip install commands.

- **`openmc_settings.md`** — Step-by-step guide for installing OpenMC (Monte Carlo neutron transport) on WSL2/Ubuntu. Covers: Chinese mirror sources (Tsinghua/USTC for apt, conda, pip), dependency installation, building from source, and cross-section data configuration. Bilingual (Chinese/English). References external blog posts and official documentation.

## Image Assets

- `background.jpeg` — Desktop background image
- `classicAvatar.png` — Avatar image
- `clqcd.png` — CLQCD (China Lattice QCD) logo
- `desktop.png` — Desktop screenshot

These are static assets referenced by configuration or documentation.
