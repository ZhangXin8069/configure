#!/usr/bin/env bash
# Open DeepSeek platform usage page in browser

echo "============================================================"
echo "  DeepSeek - Usage"
echo "============================================================"
echo
echo "  Opening https://platform.deepseek.com/usage ..."
echo

if command -v open &>/dev/null; then
    open "https://platform.deepseek.com/usage"
elif command -v xdg-open &>/dev/null; then
    xdg-open "https://platform.deepseek.com/usage"
fi
