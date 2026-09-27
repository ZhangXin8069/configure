#!/usr/bin/env bash
# Open Gitee projects in browser

echo "============================================================"
echo "  Gitee - zhangxin8069 Projects"
echo "============================================================"
echo
echo "  Opening https://gitee.com/zhangxin8069/projects ..."
echo

if command -v open &>/dev/null; then
    open "https://gitee.com/zhangxin8069/projects"
elif command -v xdg-open &>/dev/null; then
    xdg-open "https://gitee.com/zhangxin8069/projects"
fi
