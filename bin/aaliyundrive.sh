#!/usr/bin/env bash
# Open Aliyun Drive in browser

echo "============================================================"
echo "  Aliyun Drive"
echo "============================================================"
echo
echo "  Opening https://www.aliyundrive.com/drive/file/all ..."
echo

if command -v open &>/dev/null; then
    open "https://www.aliyundrive.com/drive/file/all"
elif command -v xdg-open &>/dev/null; then
    xdg-open "https://www.aliyundrive.com/drive/file/all"
fi
