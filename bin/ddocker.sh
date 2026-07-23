#!/usr/bin/env bash
# Docker Connect: counterpart of ddocker.bat for Unix (macOS / Linux)
# ============================================================================
# Step 1: Check Docker
# Step 2: Find the latest container
# Step 3: Ensure the container is running
# Step 4: Detect shell, exec in with "cd $HOME && exec <shell>"
# ============================================================================
set -euo pipefail

echo "============================================================"
echo "  Docker Connect"
echo "============================================================"
echo

pause() { read -r -p "Press Enter to continue..."; }

# ── Step 1: Check Docker ─────────────────────────────────────────────────────

echo "[1/4] Checking Docker..."

DOCKER_OK=0
if docker info &>/dev/null; then
    DOCKER_OK=1
elif docker version &>/dev/null; then
    DOCKER_OK=1
fi

if (( DOCKER_OK == 0 )); then
    echo "       Daemon not running, launching Docker Desktop..."

    # macOS: open Docker.app
    if [[ "$(uname -s)" == "Darwin" ]]; then
        if [[ -d "/Applications/Docker.app" ]]; then
            open -a Docker
        else
            echo "[FAIL] Docker Desktop not found."
            echo "       Install: brew install --cask docker"
            echo
            pause
            exit 1
        fi
    # Linux: try systemctl
    elif command -v systemctl &>/dev/null; then
        sudo systemctl start docker 2>/dev/null || {
            echo "[FAIL] Could not start Docker daemon via systemctl."
            echo
            pause
            exit 1
        }
    else
        echo "[FAIL] Docker daemon is not running."
        echo "       Please start Docker manually."
        echo
        pause
        exit 1
    fi

    # Wait for daemon (max 90s)
    for (( n = 0; n < 90; n++ )); do
        sleep 1
        if docker info &>/dev/null; then
            DOCKER_OK=1
            break
        fi
    done

    if (( DOCKER_OK == 0 )); then
        echo "[FAIL] Docker daemon did not start in 90s."
        echo
        pause
        exit 1
    fi
fi

DKR_VER=$(docker info --format '{{.ServerVersion}}' 2>/dev/null || echo "unknown")
echo "       Docker is running (v${DKR_VER})"
echo

# ── Step 2: Find container ───────────────────────────────────────────────────

echo "[2/4] Finding container..."

LATEST=$(docker ps -a --format '{{.Names}}' --latest 2>/dev/null || true)

# Fallback by ID
if [[ -z "${LATEST}" ]]; then
    CID=$(docker ps -aq --last 1 2>/dev/null || true)
    if [[ -n "${CID}" ]]; then
        LATEST=$(docker inspect -f '{{.Name}}' "${CID}" 2>/dev/null || true)
        LATEST="${LATEST#/}"   # strip leading /
    fi
fi

if [[ -n "${LATEST}" ]]; then
    echo "       Container: ${LATEST}"
    echo
else
    echo "[FAIL] No containers found."
    echo

    HAS_IMG=0
    if [[ -n "$(docker images -q 2>/dev/null || true)" ]]; then
        HAS_IMG=1
    fi

    if (( HAS_IMG == 1 )); then
        echo "  Images found. Create a container:"
        echo "    docker run -d --name test ubuntu tail -f /dev/null"
    else
        echo "  Pull an image and create a container:"
        echo "    docker pull ubuntu"
        echo "    docker run -d --name test ubuntu tail -f /dev/null"
        echo
        echo "  Guide: https://gitee.com/zhangxin8069/configure/raw/stab10/lib/_docker/setup.md"
    fi
    echo
    pause
    exit 1
fi

# ── Step 3: Ensure running ───────────────────────────────────────────────────

echo "[3/4] Checking container status..."

STATUS=$(docker inspect -f '{{.State.Status}}' "${LATEST}" 2>/dev/null || true)

if [[ "${STATUS}" == "running" ]]; then
    echo "       Already running"
else
    echo "       Status: ${STATUS} -- starting..."
    if ! docker start "${LATEST}" &>/dev/null; then
        echo "[FAIL] Could not start container."
        echo "       docker logs ${LATEST}"
        echo
        pause
        exit 1
    fi
    echo "       Started"
fi
echo

# ── Step 4: Detect shell, enter container, cd $HOME, launch zsh ──────────────

echo "[4/4] Detecting shell and opening terminal..."

SH=""
if    docker exec "${LATEST}" which bash &>/dev/null; then SH="bash"
elif  docker exec "${LATEST}" which sh   &>/dev/null; then SH="sh"
elif  docker exec "${LATEST}" test -x /bin/bash &>/dev/null; then SH="bash"
elif  docker exec "${LATEST}" test -x /bin/sh   &>/dev/null; then SH="sh"
elif  docker exec "${LATEST}" test -x /bin/ash  &>/dev/null; then SH="ash"
fi

if [[ -z "${SH}" ]]; then
    echo "[FAIL] No shell found in container."
    echo
    pause
    exit 1
fi

echo "       Base shell: /bin/${SH}"

# Check if zsh is available (preferred)
HAS_ZSH=0
if docker exec "${LATEST}" which zsh       &>/dev/null; then HAS_ZSH=1; fi
if (( HAS_ZSH == 0 )) && docker exec "${LATEST}" test -x /bin/zsh &>/dev/null; then HAS_ZSH=1; fi

if (( HAS_ZSH == 1 )); then
    FINAL="zsh"
    echo "       Using zsh"
else
    FINAL="${SH}"
fi

echo "       cd \$HOME && exec ${FINAL}"
echo "============================================================"
echo

# Launch: the shell -c runs "cd $HOME && exec <final_shell>"
# $HOME is expanded by the container's shell, not by this script
docker exec -it "${LATEST}" "${SH}" -c "cd \$HOME && exec ${FINAL} -l"
