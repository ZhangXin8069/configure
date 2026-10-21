#!/usr/bin/env python3
"""Compatibility entry point for the former Codex-only state lookup."""

import os
import sys
from pathlib import Path


target = Path(__file__).with_name("agent-session-state.py")
os.execv(sys.executable, [sys.executable, str(target), "--agent", "codex", *sys.argv[1:]])
