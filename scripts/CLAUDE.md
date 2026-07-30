# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this directory.

## Overview

This directory contains maintenance and bootstrapping scripts for the `configure` repository. Unlike `bin/`, scripts here are **not** auto-aliased — they are invoked directly by path.

## Scripts

### `script_alias.sh`

Auto-generates the alias file `tmp/scripts.sh` by scanning for `.sh` files:

1. Sources `env.sh` to set up `PATH` (needed because this script itself may be run from anywhere).
2. Emits header with timestamp into `tmp/scripts.sh`.
3. Scans `tmp/` for `.sh` files → generates `alias <name>='bash <path>'` lines.
4. Scans `bin/` for `.sh` files → generates `alias <name>='bash <path>'` lines.
5. Emits footer with timestamp.

**Run this whenever a new `.sh` file is added to or removed from `bin/` or `tmp/`.** The generated aliases take effect in new shells (or after `source ~/.zshrc`).

### `script_make.sh`

Test/prototype script generator. Creates 10 numbered test scripts (`test0.sh` ... `test9.sh`) in `tmp/`, each compiling and running a corresponding `testN.cu` CUDA file. Used for GPU code development testing.

Output goes to `tmp/test*.sh` which ARE auto-aliased (they match the `*.sh` glob), so they become available as shell commands after regeneration.

### `scripts/` subdirectory

Currently empty. Intended for additional helper scripts.

## Relationship to the System

```
scripts/script_alias.sh  ──generates──>  tmp/scripts.sh  ──sourced by──>  env.sh  ──sourced by──>  .zshrc
```

When `env.sh` is sourced (on every shell startup), it sources `tmp/scripts.sh`, making all `bin/` and `tmp/` `.sh` files available as shell aliases.
