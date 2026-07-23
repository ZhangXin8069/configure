#!/usr/bin/env bash
# Open Bilibili in browser

echo "============================================================"
echo "  Bilibili"
echo "============================================================"
echo
echo "  Opening https://www.bilibili.com/ ..."
echo

if command -v open &>/dev/null; then
    open "https://www.bilibili.com/"
elif command -v xdg-open &>/dev/null; then
    xdg-open "https://www.bilibili.com/"
fi
