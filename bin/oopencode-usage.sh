#!/usr/bin/env bash
# Open OpenCode (DeepSeek V4 Flash) usage page in browser

_PATH=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
_NAME=$(basename "${BASH_SOURCE[0]:-$0}")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

echo "============================================================"
echo "  OpenCode - Usage (DeepSeek V4 Flash)"
echo "============================================================"
echo
echo "  Opening https://opencode.ai/workspace/wrk_01KZTY1K326GTXPHTBF82TRZ80/usage ..."
echo

if command -v open &>/dev/null; then
    open "https://opencode.ai/workspace/wrk_01KZTY1K326GTXPHTBF82TRZ80/usage"
elif command -v xdg-open &>/dev/null; then
    xdg-open "https://opencode.ai/workspace/wrk_01KZTY1K326GTXPHTBF82TRZ80/usage"
else
    echo "  [warn] 未找到 open / xdg-open，请手动访问 https://opencode.ai/workspace/wrk_01KZTY1K326GTXPHTBF82TRZ80/usage"
fi

echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
