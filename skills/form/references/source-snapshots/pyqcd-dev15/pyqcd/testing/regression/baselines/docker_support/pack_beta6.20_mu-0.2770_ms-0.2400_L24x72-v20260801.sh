#!/bin/bash
#===============================================================================
# pack_gpd_data.sh
#
# Package the lattice QCD gluon PDF dataset (beta6.20, L24x72) into a portable
# tar.gz archive with an embedded extraction script.
#
# Data included:
#   - Eigenvectors & eigenvalues (per-configuration: 6250, 6450, 6650)
#   - Perambulators (mz2_my0_mx0) for confs: 6250, 6450, 6650
#   - Gauge configurations (.lime) for confs: 6250, 6450, 6650
#
# Output: /root/windows/beta6.20_mu-0.2770_ms-0.2400_L24x72.tar.gz
#
# Usage: bash /root/windows/pack_gpd_data.sh
#===============================================================================

set -euo pipefail

# ---- Configuration ----
OUTPUT="/root/windows/beta6.20_mu-0.2770_ms-0.2400_L24x72.tar.gz"
STAGING_ROOT="/tmp/staging_gpd_$$"
EIGEN_DIR="/public/group/lqcd/eigensystem/beta6.20_mu-0.2770_ms-0.2400_L24x72"
PERAMB_DIR="/public/group/lqcd/perambulators"
GAUGE_DIR="/public/group/lqcd/configurations/CLOVER"
ENSEMBLE="beta6.20_mu-0.2770_ms-0.2400_L24x72"
# CONFS=(6250 6450 6650)
CONFS=(6250 6450 6650 6850 7050 7250 7450 7650 7850 8050)

# ---- Colors ----
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m' # no color

# ---- Cleanup on exit ----
cleanup() {
    echo ""
    echo -e "${DIM}--- Cleaning staging area...${NC}"
    if [ -d "$STAGING_ROOT" ]; then
        rm -rf "$STAGING_ROOT"
        echo -e "${DIM}    Removed: $STAGING_ROOT${NC}"
    fi
    echo ""
}
trap cleanup EXIT

# ---- Progress helpers ----
print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${BOLD}[${GREEN}+${NC}${BOLD}]${NC} $1"
}

print_info() {
    echo -e "    ${DIM}$1${NC}"
}

print_warn() {
    echo -e "    ${YELLOW}⚠  $1${NC}"
}

# ---- Check prerequisites ----
print_header "Lattice QCD Gluon PDF Data Packager"

print_step "Checking prerequisites..."

# Check source files
errors=0
check_file() {
    if [ ! -e "$1" ]; then
        echo -e "    ${RED}✗ MISSING:${NC} $1"
        ((errors++))
    else
        local sz
        sz=$(du -sh "$1" 2>/dev/null | cut -f1)
        print_info "✓  $sz  $1"
    fi
}

check_file "$EIGEN_DIR"
check_file "$PERAMB_DIR/${ENSEMBLE}/light"

for conf in "${CONFS[@]}"; do
    check_file "$GAUGE_DIR/${ENSEMBLE}/${ENSEMBLE}_cfg_${conf}.lime"
done

if [ "$errors" -gt 0 ]; then
    echo ""
    echo -e "${RED}ERROR: $errors source file(s) missing. Aborting.${NC}"
    exit 1
fi

# Check output location
mkdir -p "$(dirname "$OUTPUT")"
OUTDIR=$(dirname "$OUTPUT")
print_info "Output: $OUTPUT"
print_info "Disk free on $OUTDIR: $(df -h "$OUTDIR" | awk 'NR==2{print $4}')"

# ---- Step 1: Build staging tree ----
print_header "Step 1/4: Building staging tree (hardlinks — zero data copy)"

print_step "Creating directory structure..."
STAGING="$STAGING_ROOT"
mkdir -p "$STAGING/$EIGEN_DIR"
mkdir -p "$STAGING/$PERAMB_DIR/${ENSEMBLE}/light"
mkdir -p "$STAGING/$GAUGE_DIR/${ENSEMBLE}"
print_info "Staging root: $STAGING"

# Helper: hardlink with progress count
hardlink_with_progress() {
    local src="$1" dst="$2" label="$3"
    printf "    %-65s ... " "$label"
    if cp -l "$src" "$dst" 2>/dev/null; then
        printf "${GREEN}done${NC}\n"
    else
        printf "${YELLOW}copying (no hardlink support)${NC} ... "
        cp "$src" "$dst"
        printf "${GREEN}done${NC}\n"
    fi
}

print_step "Linking eigenvector/eigenvalue directories (per-configuration)..."
for conf in "${CONFS[@]}"; do
    src_eigen="$EIGEN_DIR/$conf"
    dst_eigen="$STAGING/$EIGEN_DIR/$conf"
    nfiles=$(find "$src_eigen" -type f | wc -l)
    printf "    conf %-4s (%3d files) ... " "$conf" "$nfiles"
    if cp -lR "$src_eigen" "$dst_eigen" 2>/dev/null; then
        printf "${GREEN}done${NC}\n"
    else
        printf "${YELLOW}copying (no hardlink support)${NC} ... "
        cp -R "$src_eigen" "$dst_eigen"
        printf "${GREEN}done${NC}\n"
    fi
done

print_step "Linking gauge configurations..."
for conf in "${CONFS[@]}"; do
    hardlink_with_progress \
        "$GAUGE_DIR/${ENSEMBLE}/${ENSEMBLE}_cfg_${conf}.lime" \
        "$STAGING/$GAUGE_DIR/${ENSEMBLE}/${ENSEMBLE}_cfg_${conf}.lime" \
        "cfg_${conf}.lime"
done

print_step "Linking perambulator directories (3 configurations × ~288 files each)..."
for conf in "${CONFS[@]}"; do
    src_peramb="$PERAMB_DIR/${ENSEMBLE}/light/$conf"
    dst_peramb="$STAGING/$PERAMB_DIR/${ENSEMBLE}/light/$conf"
    nfiles=$(find "$src_peramb" -type f | wc -l)
    printf "    conf %-4s (%3d files) ... " "$conf" "$nfiles"
    if cp -lR "$src_peramb" "$dst_peramb" 2>/dev/null; then
        printf "${GREEN}done${NC}\n"
    else
        printf "${YELLOW}copying (no hardlink support)${NC} ... "
        cp -R "$src_peramb" "$dst_peramb"
        printf "${GREEN}done${NC}\n"
    fi
done

print_step "Total staging size & file count:"
STAGE_SIZE=$(du -sh "$STAGING" | cut -f1)
STAGE_FILES=$(find "$STAGING" -type f | wc -l)
echo -e "    ${BOLD}$STAGE_SIZE  |  $STAGE_FILES files${NC}"

# ---- Step 2: Create extraction script ----
print_header "Step 2/4: Writing extraction script"

cat > "$STAGING/extract.sh" << 'EXTRACTSCRIPT'
#!/bin/bash
#===============================================================================
# Extract: beta6.20_mu-0.2770_ms-0.2400_L24x72 lattice QCD gluon PDF data
#
# Configurations: 6250, 6450, 6650 (Nconf=3)
# Target ensemble: beta=6.20, mu=-0.2770, ms=-0.2400, 24³×72
#
# Usage:
#   ./extract.sh                  → extract to / (restore original paths)
#   ./extract.sh /custom/path     → extract to a custom base directory
#   TARGET=/data ./extract.sh     → via environment variable
#
# After extraction:
#   <target>/public/group/lqcd/
#   ├── eigensystem/
#   │   └── beta6.20_..._L24x72/  # per-conf eigenvector/values
#   ├── perambulators/
#   │   └── beta6.20_..._L24x72/light/  # per-conf perambulators
#   └── configurations/CLOVER/   # .lime gauge configs
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE=""

for candidate in \
    "$SCRIPT_DIR/beta6.20_mu-0.2770_ms-0.2400_L24x72.tar.gz" \
    "$(pwd)/beta6.20_mu-0.2770_ms-0.2400_L24x72.tar.gz"; do
    if [ -f "$candidate" ]; then
        ARCHIVE="$candidate"
        break
    fi
done

if [ -z "$ARCHIVE" ]; then
    echo "ERROR: Cannot find beta6.20_mu-0.2770_ms-0.2400_L24x72.tar.gz"
    echo "Place this script alongside the archive, then run again."
    exit 1
fi

TARGET="${1:-${TARGET:-/}}"

echo "═══════════════════════════════════════════════════"
echo "  Lattice QCD Gluon PDF Data — Extraction"
echo "═══════════════════════════════════════════════════"
echo "  Ensemble : beta6.20  μ=-0.2770  ms=-0.2400  24³×72"
echo "  Confs    : 6250, 6450, 6650"
echo "  Archive  : $ARCHIVE"
echo "  Target   : $TARGET"
echo "═══════════════════════════════════════════════════"
echo ""

if [ "$TARGET" != "/" ] && [ ! -d "$TARGET" ]; then
    read -rp "Target '$TARGET' does not exist. Create it? [y/N] " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
        mkdir -p "$TARGET"
    else
        echo "Aborted."
        exit 1
    fi
fi

echo "Extracting..."
if command -v pv &>/dev/null; then
    ARCHIVE_SZ=$(stat -c%s "$ARCHIVE")
    pv -s "$ARCHIVE_SZ" "$ARCHIVE" | tar -xz -C "$TARGET"
else
    tar -xzvf "$ARCHIVE" -C "$TARGET" 2>&1 | \
        awk -v total=869 'BEGIN{c=0} /^public\//{c++; p=int(c/total*100); printf "\r    [%3d%%] %d/%d files", p, c, total} END{printf "\r    [100%%] %d files extracted\n", c}'
fi

echo ""
echo "✓ Extraction complete."
echo ""
echo "Data layout:"
echo "  Eigenvectors  → $TARGET/public/group/lqcd/eigensystem/beta6.20_mu-0.2770_ms-0.2400_L24x72/"
echo "  Perambulators → $TARGET/public/group/lqcd/perambulators/beta6.20_mu-0.2770_ms-0.2400_L24x72/light/"
echo "  Gauge configs → $TARGET/public/group/lqcd/configurations/CLOVER/"
echo ""
echo "You may delete this script ($(basename "$0")) now."
EXTRACTSCRIPT

chmod +x "$STAGING/extract.sh"
print_info "Written and made executable: extract.sh"

# ---- Step 3: Show data manifest ----
print_header "Step 3/4: Data manifest"

cat << EOF
    ${BOLD}Archive contents:${NC}

    ┌──────────────────────────────────────────────────────────────────┐
    │ Ensemble : ${ENSEMBLE}                   │
    │ Volume   : 24³ × 72                                            │
    │ Nconf    : ${#CONFS[@]}  (${CONFS[*]})                                   │
    ├──────────────────────────────────────────────────────────────────┤
    │ Eigenvectors : eigensystem/${ENSEMBLE}/{${CONFS[*]}}  │
    │ Perambulators: light/{${CONFS[*]}}                              │
    │ Gauge cfgs   : ${ENSEMBLE}_cfg_{${CONFS[*]}}.lime│
    ├──────────────────────────────────────────────────────────────────┤
    │ Staging size : $STAGE_SIZE                                               │
    │ Total files  : $((STAGE_FILES + 1))  (data + extract.sh)                          │
    └──────────────────────────────────────────────────────────────────┘

EOF

# ---- Step 4: Create archive ----
print_header "Step 4/4: Creating archive"

print_step "Compressing $STAGE_SIZE of data ($STAGE_FILES data files + extract.sh)..."

ARCHIVE_SIZE=$(du -sb "$STAGING" | cut -f1)

if command -v pv &>/dev/null; then
    print_info "Using pv for progress display"
    (cd "$STAGING" && tar -cf - . ) | \
        pv -s "$ARCHIVE_SIZE" -petr | \
        gzip > "$OUTPUT"
else
    # Foreground tar with --checkpoint progress (GNU tar)
    print_warn "pv not installed — install pv for a progress bar"
    print_info "Compressing 44G in foreground, this will take a while ..."
    echo ""
    if tar --help 2>&1 | grep -q -- '--checkpoint'; then
        # GNU tar checkpoint: print a dot every 1 record (10 MiB by default)
        # Use --record-size to make dots fire more frequently for progress
        (cd "$STAGING" && tar --record-size=10240 --checkpoint=500 --checkpoint-action=dot -czf "$OUTPUT" . )
        echo ""
    else
        # POSIX tar: run verbose but pipe to awk for periodic progress
        (cd "$STAGING" && tar -cvzf "$OUTPUT" . 2>&1) | \
            awk 'NR % 50 == 0 { printf "\r    archived %d files ...", NR } END { printf "\r    archived %d files total\n", NR }'
    fi
    echo ""
fi

# Verify archive integrity before reporting success
set +e
gzip -t "$OUTPUT"
GZIP_RC=$?
set -e
if [ "$GZIP_RC" -ne 0 ]; then
    echo -e "${RED}ERROR: gzip integrity check failed! Archive may be corrupt.${NC}"
    exit 1
fi

print_info "Integrity check passed (gzip -t)"

OUT_SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')
print_step "Archive created: ${BOLD}$OUTPUT${NC} ($OUT_SIZE)"
print_info "Data files : $STAGE_FILES"
print_info "+ extract.sh"

# ---- Done ----
print_header "Done"

echo ""
echo -e "  ${GREEN}${BOLD}✓${NC}  ${BOLD}$OUTPUT${NC}"
echo ""
echo "  To extract on another machine:"
echo ""
echo -e "      ${CYAN}tar -xzf beta6.20_mu-0.2770_ms-0.2400_L24x72.tar.gz -C /${NC}"
echo "      # then run:  ./extract.sh"
echo ""
echo "  Or just run the bundled script directly:"
echo ""
echo -e "      ${CYAN}cd /root/windows && ./extract.sh${NC}"
echo -e "      ${CYAN}cd /root/windows && ./extract.sh /mnt/lqcd${NC}"
echo ""
