param(
    [Parameter(Position = 0)]
    [string]$Short
)

$numericFallbackUser = 'zhangxin'

if ([string]::IsNullOrWhiteSpace($Short)) {
    $Short = $env:SS_SHORT
}
if ([string]::IsNullOrWhiteSpace($Short)) {
    $Short = 'k'
}

$Short = $Short.ToLowerInvariant()
if ($Short -notmatch '^([a-z]*)([0-9]{0,3})([a-z]*)$') {
    [Console]::Error.WriteLine('ERROR: unsupported target: ' + $Short)
    [Console]::Error.WriteLine('Usage: ss [alias|number|alias+number]')
    [Console]::Error.WriteLine('Aliases: k, z, x, zx, y, ht, yht')
    exit 64
}

$alias = $matches[1] + $matches[3]
$digits = $matches[2]
$key = if ($alias.Length -eq 0) { 'numeric' } else { $alias }
$targets = @{
    'numeric' = @($numericFallbackUser, $null)
    'k'       = @('kfutfd', 19)
    'z'       = @('zhang', 3)
    'x'       = @('xin', 4)
    'zx'      = @('zhangxin', 2)
    'y'       = @('yang', 11)
    'ht'      = @('haotian', 12)
    'yht'     = @('yanghaotian', 13)
    'yh'      = @('yanghaotian', 13)
}

if (-not $targets.ContainsKey($key)) {
    [Console]::Error.WriteLine('ERROR: unsupported user alias: ' + $alias)
    [Console]::Error.WriteLine('Usage: ss [alias|number|alias+number]')
    [Console]::Error.WriteLine('Aliases: k, z, x, zx, y, ht, yht')
    exit 64
}

$target = $targets[$key]
if ($digits.Length -gt 0) {
    $ipSuffix = [int]$digits
    if ($ipSuffix -lt 1 -or $ipSuffix -gt 254) {
        [Console]::Error.WriteLine('ERROR: IPv4 suffix must be between 1 and 254: ' + $digits)
        exit 64
    }
}
elseif ($null -eq $target[1]) {
    [Console]::Error.WriteLine('ERROR: this alias has no default IPv4 suffix.')
    exit 64
}
else {
    $ipSuffix = [int]$target[1]
}

if ($alias.Length -eq 0) {
    $numericAliases = @{
        19 = 'k'
        20 = 'k'
        3  = 'z'
        2  = 'zx'
        4  = 'x'
        11 = 'y'
        12 = 'ht'
        13 = 'yht'
    }
    if ($numericAliases.ContainsKey($ipSuffix)) {
        $target = $targets[$numericAliases[$ipSuffix]]
    }
}

$ssh = Get-Command ssh.exe -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $ssh) {
    [Console]::Error.WriteLine('ERROR: ssh.exe was not found.')
    exit 127
}

$screenSession = $env:SSH_SCREEN_NAME
if ([string]::IsNullOrWhiteSpace($screenSession)) {
    $screenSession = $env:COMPUTERNAME
}
if ([string]::IsNullOrWhiteSpace($screenSession)) {
    $screenSession = [System.Net.Dns]::GetHostName()
}
$screenSession = $screenSession -replace '[^A-Za-z0-9_.-]', '_'

$remoteShell = $env:SSH_REMOTE_SHELL
if ([string]::IsNullOrWhiteSpace($remoteShell)) {
    $remoteShell = if ($ipSuffix -eq 19) { 'powershell' } else { 'posix' }
}
if ($remoteShell -notin @('posix', 'powershell')) {
    [Console]::Error.WriteLine('ERROR: SSH_REMOTE_SHELL must be posix or powershell.')
    exit 64
}

if ($remoteShell -eq 'powershell') {
    $remoteScreenScript = @(
        '$ErrorActionPreference = ''SilentlyContinue'''
        '$screenCommand = Get-Command screen -ErrorAction SilentlyContinue'
        '$screenTerm = ''screen'''
        '$infocmpCommand = Get-Command infocmp -ErrorAction SilentlyContinue'
        'if ($null -ne $infocmpCommand) {'
        '    & $infocmpCommand.Path screen-256color *> $null'
        '    if ($LASTEXITCODE -eq 0) { $screenTerm = ''screen-256color'' }'
        '}'
        '$hostShell = (Get-Process -Id $PID).Path'
        'if ([string]::IsNullOrWhiteSpace($hostShell)) { $hostShell = ''powershell.exe'' }'
        'if ($null -ne $screenCommand) {'
        ("    & `$screenCommand.Path -U -T `$screenTerm -S '" + $screenSession + "' -t '" + $screenSession + "'")
        '} else {'
        '    Write-Warning ''remote screen is unavailable; continuing without it.'''
        '    & $hostShell -NoLogo -NoProfile'
        '}'
    ) -join "`n"
}
else {
    $remoteScreenScript = @(
        'if command -v screen >/dev/null 2>&1; then'
        '    screen_term=screen'
        '    if command -v infocmp >/dev/null 2>&1 && infocmp screen-256color >/dev/null 2>&1; then'
        '        screen_term=screen-256color'
        '    fi'
        ("    exec screen -U -T `"`$screen_term`" -S '" + $screenSession + "' -t '" + $screenSession + "'")
        'fi'
        "printf '%s\n' '[WARN] remote screen is unavailable; continuing without it.' >&2"
        'exec "${SHELL:-/bin/sh}" -l'
    ) -join "`n"
}

$sshArguments = @(
    '-t',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-l', $target[0],
    ('192.168.188.' + $ipSuffix)
)

& $ssh.Source @sshArguments $remoteScreenScript
exit $LASTEXITCODE
