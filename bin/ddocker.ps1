#===========================================================================
# ddocker.ps1  —  Windows PowerShell 版 Docker 快速连接工具
#
# 0. 检查 Docker CLI 是否安装，未安装则显示安装指引
# 1. 检测 Docker 是否运行，未运行则尝试启动
# 2. 找到最近创建的容器，未运行则启动
# 3. 在新终端窗口中进入该容器的交互式终端
#===========================================================================

$ErrorActionPreference = "Stop"

# ── 颜色定义 ──
function Write-OK   { Write-Host "[OK]    " -ForegroundColor Green -NoNewline; Write-Host $args }
function Write-Warn { Write-Host "[WARN]  " -ForegroundColor Yellow -NoNewline; Write-Host $args }
function Write-Err  { Write-Host "[ERR]   " -ForegroundColor Red -NoNewline; Write-Host $args }
function Write-Step { Write-Host "[STEP]  " -ForegroundColor Cyan -NoNewline; Write-Host $args }

$SETUP_URL = "https://gitee.com/zhangxin8069/configure/raw/stab10/lib/_docker/setup.md"

function Print-DockerInstallGuide {
    Write-Host @"

  =============================================
    Docker 安装指引 - Windows
  =============================================

  推荐方式: Docker Desktop for Windows
    https://docs.docker.com/desktop/install/windows-install/

  方式一 - 使用 winget (Windows 10/11):
    winget install Docker.DockerDesktop

  方式二 - 使用 Chocolatey:
    choco install docker-desktop

  方式三 - 手动安装:
    1. 前往 https://docs.docker.com/desktop/install/windows-install/
    2. 下载 Docker Desktop Installer.exe
    3. 双击运行安装程序
    4. 安装完成后重启电脑
    5. 启动 Docker Desktop

  仅安装 CLI (不需要 GUI):
    winget install Docker.DockerCLI

  注意:
    - Docker Desktop 需要启用 Hyper-V 或 WSL2
    - 建议启用 WSL2 后端以获得更好的性能
    - 安装完成后请确保 Docker Desktop 正在运行
  =============================================

"@
}

# ── Helper: 检测容器内可用的 shell ──
function Detect-ContainerShell {
    param([string]$Container)

    $shells = @("bash", "sh", "ash")
    foreach ($s in $shells) {
        $result = docker exec $Container which $s 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            return $s
        }
    }
    # 备选：检查 /bin/ 下是否存在
    foreach ($s in $shells) {
        $result = docker exec $Container test -x "/bin/$s" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $s
        }
    }
    return $null
}

# ═════════════════════════════════════════════════════════════════
# 步骤 0：检查 Docker CLI 是否安装
# ═════════════════════════════════════════════════════════════════
Write-Step "检查 Docker CLI..."

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Err "Docker CLI 未找到，请先安装 Docker。"
    Print-DockerInstallGuide
    Read-Host "Press Enter to exit"
    exit 1
}
Write-OK "Docker CLI 已就绪"
Write-Host ""

# ═════════════════════════════════════════════════════════════════
# 步骤 1：确保 Docker 守护进程运行
# ═════════════════════════════════════════════════════════════════
Write-Step "检查 Docker 守护进程..."

$dockerRunning = $false
try {
    $info = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
        # 尝试获取服务器版本
        $ver = docker info --format '{{.ServerVersion}}' 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) {
            Write-OK "Docker 已在运行 (v$ver)"
        } else {
            Write-OK "Docker 已在运行"
        }
    }
} catch {
    # docker info 失败
}

if (-not $dockerRunning) {
    Write-Warn "Docker 守护进程未运行。"

    Write-Host ""
    Write-Host "  Docker Desktop 用户请:"
    Write-Host "    1. 从开始菜单启动 Docker Desktop"
    Write-Host "    2. 等待系统托盘图标变为稳定状态"
    Write-Host ""
    Write-Host "  或使用命令行启动:"
    Write-Host "    Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'"
    Write-Host ""

    $choice = Read-Host "  是否尝试启动 Docker Desktop? (y/n)"
    if ($choice -eq 'y' -or $choice -eq 'Y') {
        $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerExe) {
            Start-Process $dockerExe
            Write-OK "已启动 Docker Desktop，等待就绪..."
        } else {
            Write-Err "未找到 Docker Desktop 可执行文件。"
            Read-Host "Press Enter to exit"
            exit 1
        }
    } else {
        Write-Err "请手动启动 Docker 后重试。"
        Read-Host "Press Enter to exit"
        exit 1
    }

    # 等待 Docker 就绪，最多 60 秒 (Windows 上 Docker Desktop 启动较慢)
    $maxWait = 60
    $ready = $false
    for ($i = 1; $i -le $maxWait; $i++) {
        try {
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-OK "Docker 已就绪。"
                $ready = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 1
        if ($i % 10 -eq 0) {
            Write-Host "  已等待 $i 秒..."
        }
    }

    if (-not $ready) {
        Write-Err "Docker 启动超时 ($maxWait 秒)，请手动排查。"
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Write-Host ""

# ═════════════════════════════════════════════════════════════════
# 步骤 2：找到最近创建的容器
# ═════════════════════════════════════════════════════════════════
Write-Step "查找最近创建的容器..."

$LATEST = docker ps -a --format '{{.Names}}' --latest 2>$null
if (-not $LATEST) {
    $lastId = docker ps -aq --last 1 2>$null
    if ($lastId) {
        $name = docker inspect -f '{{.Name}}' $lastId 2>$null
        if ($name) {
            $LATEST = $name.TrimStart('/')
        }
    }
}

if (-not $LATEST) {
    Write-Err "本地没有任何容器。"

    $hasImages = $false
    $images = docker images -q 2>$null
    if ($images) { $hasImages = $true }

    Write-Host @"

  =============================================
    快速上手
  =============================================

"@

    if ($hasImages) {
        Write-Host "  本地已有镜像，执行以下命令创建并进入容器:"
        Write-Host ""
        Write-Host "  1. 查看本地镜像:"
        Write-Host "    docker images"
        Write-Host ""
        Write-Host "  2. 创建容器 (以 ubuntu 为例):"
        Write-Host "    docker run -d --name my-ubuntu ubuntu tail -f /dev/null"
        Write-Host ""
        Write-Host "  3. 再次运行本脚本即可自动连接。"
    } else {
        Write-Host "  你的机器上还没有任何 Docker 镜像或容器。"
        Write-Host "  按以下步骤开始:"
        Write-Host ""
        Write-Host "  第 1 步 - 拉取镜像 (任选一个):"
        Write-Host "    docker pull alpine        # ~5MB, 最轻量"
        Write-Host "    docker pull ubuntu        # ~78MB, 常用"
        Write-Host "    docker pull debian        # ~124MB"
        Write-Host ""
        Write-Host "  第 2 步 - 创建后台容器:"
        Write-Host "    docker run -d --name test alpine tail -f /dev/null"
        Write-Host ""
        Write-Host "  第 3 步 - 再次运行本脚本即可自动连接。"
        Write-Host ""
        Write-Host "  详细配置和更多镜像请参考:"
        Write-Host "    $SETUP_URL"
    }

    Write-Host ""
    Write-Host "  ============================================="
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-OK "最近创建的容器: $LATEST"
Write-Host ""

# ═════════════════════════════════════════════════════════════════
# 步骤 3：确保容器在运行
# ═════════════════════════════════════════════════════════════════
$STATUS = docker inspect -f '{{.State.Status}}' $LATEST 2>$null

if ($STATUS -eq "running") {
    Write-OK "容器 $LATEST 已在运行。"
} else {
    Write-Warn "容器 $LATEST 状态为 $STATUS，正在启动..."
    docker start $LATEST 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "容器启动失败。检查: docker logs `"$LATEST`""
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-OK "容器已启动。"
}
Write-Host ""

# ═════════════════════════════════════════════════════════════════
# 步骤 4：进入容器终端（新窗口）
# ═════════════════════════════════════════════════════════════════
Write-Step "检测容器内可用的 shell..."

$CONTAINER_SHELL = Detect-ContainerShell -Container $LATEST

if (-not $CONTAINER_SHELL) {
    Write-Err "容器内没有 bash / sh / ash，无法进入终端。"
    Read-Host "Press Enter to exit"
    exit 1
}

Write-OK "找到 /bin/$CONTAINER_SHELL"
Write-Host ""

# 在当前终端中进入容器（远程/SSH 友好）
Write-Host "  Container: $LATEST"
Write-Host "  Shell:     /bin/$CONTAINER_SHELL"
Write-Host ""
docker exec -it $LATEST $CONTAINER_SHELL
