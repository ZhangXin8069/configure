#===========================================================================
# ccloudmusic.ps1  —  Windows PowerShell 版网易云音乐快速启动工具
#
# 1. 检查 CloudMusic 是否已在运行
# 2. 查找可执行文件路径（多路径 + 注册表回退）
# 3. 若未运行则启动
#===========================================================================

$ErrorActionPreference = "Stop"

# ── 颜色定义 ──
function Write-OK   { Write-Host "[OK]    " -ForegroundColor Green -NoNewline; Write-Host $args }
function Write-Warn { Write-Host "[WARN]  " -ForegroundColor Yellow -NoNewline; Write-Host $args }
function Write-Err  { Write-Host "[ERR]   " -ForegroundColor Red -NoNewline; Write-Host $args }
function Write-Step { Write-Host "[STEP]  " -ForegroundColor Cyan -NoNewline; Write-Host $args }

# ═════════════════════════════════════════════════════════════════
# 步骤 1：检查 CloudMusic 是否已在运行
# ═════════════════════════════════════════════════════════════════
Write-Step "检查网易云音乐..."

$cmProcess = Get-Process -Name "cloudmusic" -ErrorAction SilentlyContinue

if ($cmProcess) {
    Write-OK "网易云音乐已在运行。"
    Read-Host "Press Enter to exit"
    exit 0
}

Write-OK "未运行，准备启动。"
Write-Host ""

# ═════════════════════════════════════════════════════════════════
# 步骤 2：查找可执行文件
# ═════════════════════════════════════════════════════════════════
Write-Step "查找网易云音乐可执行文件..."

$cmExe = $null

# 按优先级尝试已知路径
$knownPaths = @(
    "C:\Program Files\NetEase\CloudMusic\cloudmusic.exe",
    "$env:ProgramFiles\NetEase\CloudMusic\cloudmusic.exe",
    "$env:LocalAppData\NetEase\CloudMusic\cloudmusic.exe",
    "D:\Program Files\NetEase\CloudMusic\cloudmusic.exe"
)

foreach ($p in $knownPaths) {
    if (Test-Path $p) {
        $cmExe = $p
        break
    }
}

# 回退：注册表查询
if (-not $cmExe) {
    try {
        $regPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\cloudmusic.exe"
        if (Test-Path $regPath) {
            $cmExe = (Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue).'(default)'
        }
    } catch { }
}

if (-not $cmExe) {
    Write-Err "未找到网易云音乐。"
    Write-Host @"

  =============================================
    安装指引
  =============================================

  方式一 - 官网下载:
    https://music.163.com/

  方式二 - 使用 winget:
    winget install NetEase.CloudMusic

  =============================================

"@
    Read-Host "Press Enter to exit"
    exit 1
}

Write-OK "找到: $cmExe"
Write-Host ""

# ═════════════════════════════════════════════════════════════════
# 步骤 3：启动 CloudMusic
# ═════════════════════════════════════════════════════════════════
Write-Step "启动网易云音乐..."

try {
    Start-Process -FilePath $cmExe
} catch {
    Write-Err "启动失败: $_"
    Read-Host "Press Enter to exit"
    exit 1
}

# 等待进程出现（最多 30 秒）
$maxWait = 30
$started = $false
for ($i = 1; $i -le $maxWait; $i++) {
    $p = Get-Process -Name "cloudmusic" -ErrorAction SilentlyContinue
    if ($p) {
        Write-OK "网易云音乐已启动。"
        $started = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (-not $started) {
    Write-Warn "30 秒内未检测到进程，可能仍在加载中..."
}

Write-Host ""
