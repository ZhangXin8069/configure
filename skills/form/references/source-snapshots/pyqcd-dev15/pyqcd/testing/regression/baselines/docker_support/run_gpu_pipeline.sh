#!/usr/bin/env bash
# ============================================================================
#  run_gpu_pipeline.sh — One-click launcher for the GPU distillation pipelines
#  Delegates computation to the frozen legacy pipeline.
#  Sub-commands: test / run / check / status /
#  plots / report / package / clean.
#
#  Usage examples:
#    bash run_gpu_pipeline.sh check      # verify GPU env + data paths
#    bash run_gpu_pipeline.sh test       # single-config quick test
#    bash run_gpu_pipeline.sh run        # full run (all configs, all steps)
#    bash run_gpu_pipeline.sh run --conf-ids 6250,6450 --skip-4pt   # pass-through args
#    bash run_gpu_pipeline.sh status     # summary of the latest run
#    bash run_gpu_pipeline.sh plots      # regenerate plots from saved data
#    bash run_gpu_pipeline.sh report     # compile the latest LaTeX report
#    bash run_gpu_pipeline.sh package    # tar.gz the latest run (plots+log+report)
#    bash run_gpu_pipeline.sh clean      # remove all output_* dirs (DANGER)
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LATEST="$(cd "${SCRIPT_DIR}/../legacy_pipeline" && pwd)"
if [ ! -f "${LATEST}/run_pipeline.py" ]; then
    echo "ERROR: frozen legacy pipeline not found under ${LATEST}" >&2
    exit 1
fi
LATEST_NAME="legacy_pipeline"

# ── Locate the most recent run output directory (flat `output_*` or nested
#    `output/output_*` layouts) ─────────────────────────────────────────────
resolve_latest_run() {
    local out_dir="$1"
    ls -dt "${out_dir}"/output_*/ 2>/dev/null | head -1
}
LATEST_OUT="${LATEST%/}/output"
LATEST_RUN="$(resolve_latest_run "$LATEST_OUT")"
[ -z "$LATEST_RUN" ] && LATEST_RUN="$(resolve_latest_run "$LATEST")"
LATEST_RUN="${LATEST_RUN%/}"

usage() {
    cat <<EOF
run_gpu_pipeline.sh — GPU distillation pipeline launcher

Pipeline: ${LATEST_NAME}  (${LATEST})

Usage: bash run_gpu_pipeline.sh <command> [args...]

Commands:
  check        Verify GPU environment, Python modules and data paths (step env)
  test         Single-config quick smoke test (~15 min, skips 3pt/4pt/report)
  run [args]   Full pipeline run — pass-through args to run_pipeline.py
               (e.g. --conf-ids 6250,6450 --precision complex128 --skip-4pt)
  status       Show the latest run: config, meff summary, timing, plots
  plots        Regenerate plots from saved data (analysis/plots steps only)
  report       Compile the latest LaTeX report (report.py)
  package      tar.gz the latest run (plots + logs + report + config)
  clean        Remove all output_* dirs of the latest pipeline (DANGER)
  help         Show this message

Data paths are fixed in ${LATEST_NAME}/config.py (cluster filesystem).
EOF
}

require_latest_run() {
    if [ -z "$LATEST_RUN" ]; then
        echo "ERROR: no output run found under ${LATEST}. Run 'run' or 'test' first." >&2
        exit 1
    fi
}

# ── check: environment + data path verification ────────────────────────────
cmd_check() {
    echo "=== GPU pipeline environment check (${LATEST_NAME}) ==="
    ( cd "$LATEST" && python run_pipeline.py --steps env )
}

# ── test: single-config smoke test ─────────────────────────────────────────
cmd_test() {
    echo "=== Smoke test: single config 6250 (skip 3pt/4pt/report) ==="
    ( cd "$LATEST" && python run_pipeline.py --conf-ids 6250 --skip-3pt --skip-4pt --skip-report )
}

# ── run: full pipeline (pass-through args) ─────────────────────────────────
cmd_run() {
    echo "=== Full pipeline run (${LATEST_NAME}) ==="
    ( cd "$LATEST" && python run_pipeline.py "$@" )
}


# ── status: summarize the latest run ───────────────────────────────────────
cmd_status() {
    require_latest_run
    echo "=== Latest run: ${LATEST_RUN} ==="
    if [ -f "${LATEST_RUN}/run_config.json" ]; then
        echo "--- run_config.json ---"
        python3 -c "import json;print(json.dumps(json.load(open('${LATEST_RUN}/run_config.json')),indent=1,ensure_ascii=False))" 2>/dev/null || cat "${LATEST_RUN}/run_config.json"
    fi
    if [ -f "${LATEST_RUN}/analysis_summary.json" ]; then
        echo "--- analysis_summary.json (meff) ---"
        python3 -c "
import json
d=json.load(open('${LATEST_RUN}/analysis_summary.json'))
m=d.get('meff',{})
for k,v in m.items():
    print(f'  {k:12s} E0={v.get(\"E0\",\"-\"):>10} ± {v.get(\"E0_err\",\"-\"):<10} plateau={v.get(\"plateau\")} npts={v.get(\"npts\")}')
print('  timing:', d.get('timing_s'))
" 2>/dev/null
    fi
    echo "--- plots ---"
    ls -lh "${LATEST_RUN}"/plots/*.png 2>/dev/null | awk '{print "  "$5"  "$9}' || echo "  (no plots)"
    echo "--- log (tail) ---"
    local logf="${LATEST_RUN}/run.log"
    [ -f "$logf" ] && tail -n 15 "$logf" || echo "  (no run.log in output dir; see /root/PyQCD/logs/)"
}

# ── plots: regenerate from saved data ──────────────────────────────────────
cmd_plots() {
    require_latest_run
    echo "=== Regenerating plots from ${LATEST_RUN} ==="
    ( cd "$LATEST" && python run_pipeline.py --run-dir "${LATEST_RUN}" --steps analysis,plots )
}

# ── report: compile latest LaTeX report ────────────────────────────────────
cmd_report() {
    require_latest_run
    echo "=== Compiling LaTeX report for ${LATEST_RUN} ==="
    ( cd "$LATEST" && python report.py --run-dir "${LATEST_RUN}" --out "${SCRIPT_DIR}/logs" )
}

# ── package: tar.gz the latest run ─────────────────────────────────────────
cmd_package() {
    require_latest_run
    local base
    base="$(basename "${LATEST_RUN}")"
    local pkg="${LATEST}/${base}.tar.gz"
    echo "=== Packaging ${LATEST_RUN} -> ${pkg} ==="
    tar -C "${LATEST_OUT}" -czf "${pkg}" "$(basename "${LATEST_RUN}")"
    [ -f "${LATEST_RUN}/physics_report.pdf" ] && {
        cp "${LATEST_RUN}/physics_report.pdf" "${LATEST_RUN}/report.pdf"
        tar -C "${LATEST_OUT}" -uzf "${pkg}" "$(basename "${LATEST_RUN}")/report.pdf"
    }
    echo "Packaged: ${pkg} ($(du -h "${pkg}" | cut -f1))"
}

# ── clean: remove all output runs (DANGER) ─────────────────────────────────
cmd_clean() {
    echo "Removing all output_* dirs under ${LATEST_OUT} ..."
    rm -rf "${LATEST_OUT}"/output_* 2>/dev/null
    rm -rf "${LATEST}"/output_* 2>/dev/null
    echo "Done."
}

# ── dispatch ───────────────────────────────────────────────────────────────
case "${1:-help}" in
    check)   cmd_check ;;
    test)    cmd_test ;;
    run)     shift; cmd_run "$@" ;;
    status)  cmd_status ;;
    plots)   cmd_plots ;;
    report)  cmd_report ;;
    package) cmd_package ;;
    clean)   cmd_clean ;;
    help|-h|--help) usage ;;
    *)       echo "Unknown command: ${1:-}" >&2; usage; exit 2 ;;
esac
