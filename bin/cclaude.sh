#!/usr/bin/env bash
# Launch Claude Code with auto permission mode

echo "============================================================"
echo "  Claude Code (permission-mode: auto)"
echo "============================================================"
echo

claude --permission-mode auto "$@"
