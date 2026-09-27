#!/usr/bin/env bash
# test0 —— pyqcd 蒸馏管线一致性测试运行脚本（RTX 4060 8GB 小卡）
#
# 每次运行创建版本目录 artifacts/run_<YYYYMMDDHHMM>/，全部产物（中间数据、
# 图表、LaTeX 报告、env.json、运行日志、一致性验证 JSON）落在该目录，
# 互不覆盖，可跨环境横向比对（test12 约定）。
#
# 流程：env 自检 → run（默认全量 10 组态 9 步）→ verify → check → collect。
# 冒烟模式：TEST0_SMOKE=1 时仅 1 组态（conf6250）→ verify。
#
# 用法：
#   bash pyqcd/testing/regression/distillation/run-local.sh
#   TEST0_SMOKE=1 bash pyqcd/testing/regression/distillation/run-local.sh
#   bash pyqcd/testing/regression/distillation/run-local.sh --dry-run
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
WORK="$SCRIPT_DIR"
MAIN="$WORK/main.py"
TS=$(date +%Y%m%d-%H%M%S)

# ---- 版本目录：run_<YYYYMMDDHHMM>；同分钟重跑加 -<SS> 防覆盖 ----
VDIR="$WORK/artifacts/run_$(date +%Y%m%d%H%M)"
if [ -e "$VDIR" ]; then VDIR="$VDIR-$(date +%S)"; fi
mkdir -p "$VDIR"
export TEST0_OUTDIR="$VDIR"
LOG_FILE="$VDIR/run-local-$TS.log"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

step() { echo; echo "===== $1 ====="; }
run() { # $1=timeout_s  "$@"=command
  local tmo="$1"; shift
  if [ "$DRY" = "1" ]; then echo "[dry-run] timeout $tmo $*"; return 0; fi
  echo ">>> timeout $tmo $*"
  timeout "$tmo" "$@"
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "[warn] 上一步失败 rc=$rc（继续）" >&2
  fi
  return $rc
}

# ---- 环境与完整输出归档 ----
cd "$REPO" || exit 1
source ./env.sh >/dev/null 2>&1
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== test0 local runner start $(date) ==="
echo "版本目录: $VDIR"
echo "GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)"
python "$MAIN" env || echo "[warn] env 自检失败"

if [ "${TEST0_SMOKE:-0}" = "1" ]; then
  step "Step 1: 冒烟运行（conf6250 全 9 步）"
  run 7200 python "$MAIN" run --conf-ids 6250
else
  step "Step 1: 全量运行（10 组态，9 步，参考 ~3-5h）"
  run 21600 python "$MAIN" run
fi

step "Step 2: 一致性验证（vs output_20260802_120104）"
run 1800 python "$MAIN" verify --run-dir "$VDIR"

step "Step 3: 断言门（n_fail=0 且无缺文件）"
run 300 python "$MAIN" check --run-dir "$VDIR"

step "Step 4: 产物清单"
run 300 python "$MAIN" collect --run-dir "$VDIR"

echo
echo "=== 完成。完整输出: $LOG_FILE ==="
echo "版本目录: $VDIR"
echo "跨环境比对：各环境各跑一次本脚本，v* 目录下同名产物可直接 diff/叠图。"
