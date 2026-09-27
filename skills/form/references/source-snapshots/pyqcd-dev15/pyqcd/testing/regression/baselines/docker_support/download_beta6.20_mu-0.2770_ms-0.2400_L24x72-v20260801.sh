#!/bin/bash
#=============================================================================
# Download SNSC data for snsc-v20260726 validation pipeline
#
# Usage:
#   bash download_data.sh              # interactive, confirm each download
#   bash download_data.sh --dry-run    # show what would be downloaded
#   bash download_data.sh --yes        # skip confirmation, download all
#
# Data: L24x72 ensemble, confs 6250/6450/6650, Nev=100, Pz=-2
#=============================================================================

set -euo pipefail

# --- SSH connection (with multiplexing to avoid repeated logins) ---
SSH_HOST="222.200.137.16"
SSH_PORT="10023"
SSH_USER="zhangxin"

# SSH ControlMaster: reuse a single SSH connection for all rsync/scp calls
SSH_CONTROL_DIR="/tmp/ssh-control-$$"
SSH_CONTROL_PATH="${SSH_CONTROL_DIR}/sock-%r@%h:%p"

# Common ControlMaster options (works with ssh, scp, and rsync -e)
SSH_CTL_OPTS="-o ControlMaster=auto -o ControlPath=${SSH_CONTROL_PATH} -o ControlPersist=600"
SSH_OPTS="-p ${SSH_PORT} -l ${SSH_USER} ${SSH_CTL_OPTS}"
# scp uses -P (uppercase) for port; other -o options are identical
SCP_OPTS="${SSH_CTL_OPTS} -P ${SSH_PORT}"

# --- Conf IDs ---
# CONF_IDS=(6250 6450 6650)
CONF_IDS=(6850 7050 7250 7450 7650 7850 8050)

# --- File lists ---
EIGENSYSTEM_BASE="/public/group/lqcd/eigensystem/beta6.20_mu-0.2770_ms-0.2400_L24x72"

PERAMBULATOR_BASE="/public/group/lqcd/perambulators/beta6.20_mu-0.2770_ms-0.2400_L24x72/light"
GAUGE_CONFIG_BASE="/public/group/lqcd/configurations/CLOVER/beta6.20_mu-0.2770_ms-0.2400_L24x72"

# --- Detect transfer tool ---
TRANSFER_TOOL=""
if command -v rsync &>/dev/null; then
    TRANSFER_TOOL="rsync"
elif command -v scp &>/dev/null; then
    TRANSFER_TOOL="scp"
else
    echo -e "\033[1;31m[ERROR]\033[0m Neither rsync nor scp found. Please install one of them."
    exit 1
fi

# --- Flags ---
DRY_RUN=false
SKIP_CONFIRM=false
SKIP_EXISTING=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --yes|-y)  SKIP_CONFIRM=true ;;
        --skip-existing|--resume) SKIP_EXISTING=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--yes] [--skip-existing] [--help]"
            echo ""
            echo "  --dry-run          Show what would be downloaded without transferring"
            echo "  --yes, -y          Skip per-file confirmation prompts"
            echo "  --skip-existing    Skip files/dirs that already exist with correct size"
            echo "                     (safe to re-run after an interrupted download)"
            exit 0
            ;;
    esac
done

# --- Transfer counters ---
COUNT_SKIPPED=0
COUNT_DONE=0
COUNT_FAILED=0

# --- Helper functions ---
log_info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
log_warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
log_error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; }
log_done()  { echo -e "\033[1;32m[DONE]\033[0m  $*"; }
log_skip()  { echo -e "\033[1;90m[SKIP]\033[0m  $*"; }
log_step()  { echo -e "\n\033[1;36m==== $* ====\033[0m"; }

# Check if a local file matches the remote file size.
# Returns 0 (match) if sizes equal, 1 (mismatch) otherwise.
file_already_downloaded() {
    local remote_path="$1"
    local local_path="${remote_path}"

    if [ ! -f "${local_path}" ]; then
        return 1  # local file missing
    fi

    local remote_size
    remote_size=$(ssh ${SSH_OPTS} ${SSH_HOST} \
        "stat -c%s '${remote_path}' 2>/dev/null || echo ''" 2>/dev/null)
    if [ -z "$remote_size" ]; then
        return 1  # can't stat remote — transfer just in case
    fi

    local local_size
    local_size=$(stat -c%s "${local_path}" 2>/dev/null)

    if [ "$remote_size" = "$local_size" ]; then
        return 0  # files match — safe to skip
    fi
    return 1  # sizes differ — need to re-download (or resume partial)
}

# Check if a directory has been fully downloaded.
# Compares remote file list (path + size) against local.
# Returns 0 (fully synced) or 1 (missing/mismatched files).
dir_already_downloaded() {
    local remote_dir="$1"
    local local_dir="${remote_dir}"

    if [ ! -d "${local_dir}" ]; then
        return 1  # local directory doesn't exist yet
    fi

    # Get remote file list: "size path" (relative to remote_dir)
    local remote_files
    remote_files=$(ssh ${SSH_OPTS} ${SSH_HOST} \
        "cd '${remote_dir}' 2>/dev/null && find . -type f -exec stat -c'%s %n' {} \;" 2>/dev/null)
    if [ -z "$remote_files" ]; then
        return 1  # can't list remote — transfer just in case
    fi

    # Compare each remote file against local
    local mismatch=0
    while IFS= read -r line; do
        local remote_size="${line%% *}"
        local rel_path="${line#* }"   # e.g. "./perams.6250.npy"
        local local_file="${local_dir}/${rel_path#./}"

        if [ ! -f "${local_file}" ]; then
            mismatch=1
            break
        fi
        local local_size
        local_size=$(stat -c%s "${local_file}" 2>/dev/null)
        if [ "$remote_size" != "$local_size" ]; then
            mismatch=1
            break
        fi
    done <<< "$remote_files"

    return $mismatch
}

# Download a single file via rsync or scp over SSH
# Usage: download_file <remote_path>
download_file() {
    local remote_path="$1"
    local local_path="${remote_path}"   # preserve original path structure
    local local_dir
    local_dir=$(dirname "${local_path}")

    # Create local directory
    if ! $DRY_RUN; then
        mkdir -p "${local_dir}"
    fi

    echo "  Remote: ${SSH_USER}@${SSH_HOST}:${remote_path}"
    echo "  Local:  ${local_path}"

    if $DRY_RUN; then
        log_info "[DRY-RUN] Would download: ${remote_path}"
        return 0
    fi

    # --- Skip if already fully downloaded ---
    if $SKIP_EXISTING && file_already_downloaded "${remote_path}"; then
        log_skip "Already downloaded (size match): ${local_path}"
        COUNT_SKIPPED=$((COUNT_SKIPPED + 1))
        return 0
    fi

    if ! $SKIP_CONFIRM; then
        read -r -p "  Download? [Y/n] " answer
        answer=${answer:-Y}
        if [[ ! "$answer" =~ ^[Yy]$ ]]; then
            log_warn "Skipped by user: ${remote_path}"
            COUNT_SKIPPED=$((COUNT_SKIPPED + 1))
            return 0
        fi
    fi

    if [ "$TRANSFER_TOOL" = "rsync" ]; then
        # --partial keeps partial files so next run can resume them
        rsync -avP --partial -e "ssh ${SSH_OPTS}" \
            "${SSH_USER}@${SSH_HOST}:${remote_path}" \
            "${local_path}"
    else
        scp ${SCP_OPTS} \
            "${SSH_USER}@${SSH_HOST}:${remote_path}" \
            "${local_path}"
    fi

    if [ $? -eq 0 ]; then
        log_done "Downloaded: ${local_path}"
        COUNT_DONE=$((COUNT_DONE + 1))
    else
        log_error "Failed: ${remote_path}"
        COUNT_FAILED=$((COUNT_FAILED + 1))
        return 1
    fi
}

# Download entire directory via rsync or scp over SSH
# Usage: download_dir <remote_dir>
download_dir() {
    local remote_dir="$1"
    local local_dir="${remote_dir}"     # preserve original path structure

    echo "  Remote: ${SSH_USER}@${SSH_HOST}:${remote_dir}/"
    echo "  Local:  ${local_dir}/"

    if $DRY_RUN; then
        log_info "[DRY-RUN] Would download directory: ${remote_dir}/"
        return 0
    fi

    # --- Skip if already fully synced ---
    if $SKIP_EXISTING && dir_already_downloaded "${remote_dir}"; then
        log_skip "Already fully synced: ${local_dir}/"
        COUNT_SKIPPED=$((COUNT_SKIPPED + 1))
        return 0
    fi

    if ! $SKIP_CONFIRM; then
        read -r -p "  Download entire directory? [Y/n] " answer
        answer=${answer:-Y}
        if [[ ! "$answer" =~ ^[Yy]$ ]]; then
            log_warn "Skipped by user: ${remote_dir}/"
            COUNT_SKIPPED=$((COUNT_SKIPPED + 1))
            return 0
        fi
    fi

    mkdir -p "${local_dir}"

    if [ "$TRANSFER_TOOL" = "rsync" ]; then
        # --partial keeps partial files for resume on next run
        # --partial-dir places partials in a hidden dir to avoid confusing completed files
        rsync -avP --partial --partial-dir=.rsync-partial -e "ssh ${SSH_OPTS}" \
            "${SSH_USER}@${SSH_HOST}:${remote_dir}/" \
            "${local_dir}/"
    else
        scp -r ${SCP_OPTS} \
            "${SSH_USER}@${SSH_HOST}:${remote_dir}/"* \
            "${local_dir}/"
    fi

    if [ $? -eq 0 ]; then
        log_done "Downloaded dir: ${local_dir}/"
        COUNT_DONE=$((COUNT_DONE + 1))
    else
        log_error "Failed: ${remote_dir}/"
        COUNT_FAILED=$((COUNT_FAILED + 1))
        return 1
    fi
}

# =============================================================================
# Main
# =============================================================================

echo "============================================================================="
echo " SNSC Data Download — snsc-v20260726 Validation Pipeline"
echo "============================================================================="
echo " SSH:   ssh ${SSH_OPTS} ${SSH_HOST}"
echo " Conf:  ${CONF_IDS[*]} (Nconf=${#CONF_IDS[@]})"
echo " Tool:  ${TRANSFER_TOOL}"
echo " Mode:  $($DRY_RUN && echo 'DRY-RUN' || echo 'LIVE transfer')$($SKIP_EXISTING && echo ' + skip-existing')"
echo "============================================================================="

# Set up SSH multiplexing socket directory + cleanup trap
mkdir -p "${SSH_CONTROL_DIR}"
cleanup_ssh_master() {
    if [ -S "${SSH_CONTROL_PATH}" ]; then
        ssh -O exit ${SSH_OPTS} ${SSH_HOST} 2>/dev/null || true
    fi
    rm -rf "${SSH_CONTROL_DIR}"
}
trap cleanup_ssh_master EXIT

# Test SSH connection (this also establishes the master connection)
if ! $DRY_RUN; then
    log_info "Establishing SSH master connection..."
    if ssh ${SSH_OPTS} ${SSH_HOST} -o ConnectTimeout=10 "echo OK" 2>/dev/null; then
        log_done "SSH master connection established (socket: ${SSH_CONTROL_PATH})"
    else
        log_error "Cannot connect to ${SSH_HOST}:${SSH_PORT}. Check network/VPN."
        rm -rf "${SSH_CONTROL_DIR}"
        exit 1
    fi
fi

# ---- Step 1: Eigen system ----
log_step "Step 1/4: Eigenvectors & Eigenvalues (per-configuration)"

for conf_id in "${CONF_IDS[@]}"; do
    eigen_dir="${EIGENSYSTEM_BASE}/${conf_id}"
    echo ""
    log_info "Conf ${conf_id}: ${eigen_dir}/"
    download_dir "${eigen_dir}"
done

# ---- Step 2: Perambulators ----
log_step "Step 2/4: Perambulators (mom_smear=-2, Pz=-2)"

for conf_id in "${CONF_IDS[@]}"; do
    peram_dir="${PERAMBULATOR_BASE}/${conf_id}"
    echo ""
    log_info "Conf ${conf_id}: ${peram_dir}/"
    download_dir "${peram_dir}"
done

# ---- Step 3: Gauge configurations ----
log_step "Step 3/4: Gauge Configurations (.lime ILDG format)"

for conf_id in "${CONF_IDS[@]}"; do
    gauge_file="${GAUGE_CONFIG_BASE}/beta6.20_mu-0.2770_ms-0.2400_L24x72_cfg_${conf_id}.lime"
    echo ""
    log_info "Conf ${conf_id}: ${gauge_file}"
    download_file "${gauge_file}"
done

# ---- Step 4: Summary ----
log_step "Step 4/4: Summary"

echo ""
echo "Expected local file tree:"
echo ""
echo "  /public/group/lqcd/"
echo "  ├── eigensystem/"
echo "      └── beta6.20_..._L24x72/"
for conf_id in "${CONF_IDS[@]}"; do
echo "          └── ${conf_id}/   (eigenvector.npy, eigenvalue.npy)"
done
echo "  ├── perambulators/"
echo "      └── beta6.20_..._L24x72/light/"
for conf_id in "${CONF_IDS[@]}"; do
echo "          └── ${conf_id}/   (perams.*.${conf_id}.*)"
done
echo "  └── configurations/CLOVER/"
echo "      └── beta6.20_..._L24x72/"
for conf_id in "${CONF_IDS[@]}"; do
echo "          ├── beta6.20_..._cfg_${conf_id}.lime"
done

echo ""
echo "============================================================================="
if $DRY_RUN; then
    log_info "DRY-RUN complete. Remove --dry-run to actually download."
else
    echo "  Skipped:  ${COUNT_SKIPPED} (already present / user declined)"
    echo "  Done:     ${COUNT_DONE}"
    echo "  Failed:   ${COUNT_FAILED}"
    echo ""
    if [ "${COUNT_FAILED}" -eq 0 ]; then
        log_done "All downloads complete."
    else
        log_warn "${COUNT_FAILED} transfer(s) failed. Re-run with --skip-existing to retry."
    fi
fi
echo "============================================================================="
