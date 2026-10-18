@echo off
setlocal EnableExtensions
chcp 65001 >nul
title SS Connect

set "_PATH=%~dp0"
set "_NAME=%~nx0"
echo ###%_NAME% in %_PATH% is running...:%date% %time%###

if not "%~2"=="" (
    echo 错误：ss 只接受一个缩写、数字或组合参数。
    set "_RC=64"
    goto finish
)

set "_SHORT=%~1"
if not defined _SHORT set "_SHORT=k"
set "SS_SHORT=%_SHORT%"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$arg = $env:SS_SHORT; if ($arg -notmatch '^([A-Za-z]*)([0-9]{0,3})([A-Za-z]*)$') { [Console]::Error.WriteLine('错误：不支持的目标。'); exit 64 }; $alias = ($matches[1] + $matches[3]).ToLowerInvariant(); $digits = $matches[2]; $key = $alias; if ($key.Length -eq 0) { $key = 'numeric' }; $map = @{ 'numeric' = @('zhangxin', $null); 'k' = @('kfutfd', 19); 'z' = @('zhang', 3); 'x' = @('xin', 4); 'zx' = @('zhangxin', 2); 'y' = @('yang', 11); 'ht' = @('haotian', 12); 'yht' = @('yanghaotian', 13); 'yh' = @('yanghaotian', 13) }; if (-not $map.ContainsKey($key)) { [Console]::Error.WriteLine('错误：不支持的用户缩写：' + $alias); exit 64 }; $entry = $map[$key]; if ($digits.Length -gt 0) { $ip = [int]$digits; if ($ip -lt 1 -or $ip -gt 254) { [Console]::Error.WriteLine('错误：IPv4 末位必须在 1-254 之间：' + $digits); exit 64 } } else { if ($null -eq $entry[1]) { [Console]::Error.WriteLine('错误：该用户缩写缺少默认 IPv4 末位。'); exit 64 }; $ip = [int]$entry[1] }; if ($alias.Length -eq 0) { $numericAliases = @{ 19 = 'k'; 3 = 'z'; 2 = 'zx'; 4 = 'x'; 11 = 'y'; 12 = 'ht'; 13 = 'yht' }; if ($numericAliases.ContainsKey($ip)) { $entry = $map[$numericAliases[$ip]] } }; $ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue; if ($null -eq $ssh) { [Console]::Error.WriteLine('错误：未找到 ssh.exe。'); exit 127 }; & $ssh.Source ('192.168.188.' + $ip) -l $entry[0]; exit $LASTEXITCODE"
set "_RC=%errorlevel%"

:finish
echo ###%_NAME% in %_PATH% is done......:%date% %time%###
endlocal & exit /b %_RC%
