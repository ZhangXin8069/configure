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

& $ssh.Source ('192.168.188.' + $ipSuffix) -l $target[0]
exit $LASTEXITCODE
