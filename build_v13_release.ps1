$ErrorActionPreference = "Stop"

Write-Output "========================================"
Write-Output " BUILD: LingShu v1.3 (Release)"
Write-Output "========================================"

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$projectRoot = $PWD.Path
Write-Output "Project: $projectRoot"

$srcScript = Join-Path $projectRoot "packaging\build_first_exe_fast.ps1"
$bytes = [System.IO.File]::ReadAllBytes($srcScript)
$text = [System.Text.Encoding]::UTF8.GetString($bytes)

# Strip ALL leading BOM / ZWNBSP characters (fixes double BOM issue)
$bomChar = [char]0xFEFF
$text = $text.TrimStart($bomChar)

# Replace Chinese chars in param() defaults to avoid PS 5.1 encoding issues
$ling = [char]0x7075
$shu = [char]0x67a2
$chineseName = "$ling$shu"
$old = '[string]$ProductName = "' + $chineseName + '"'
$new = '[string]$ProductName = "LingShu"'
$text = $text.Replace($old, $new)

# Write temp script with BOM
$tmpFile = Join-Path $env:TEMP "lingshu_build_v13.ps1"
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
[System.IO.File]::WriteAllText($tmpFile, $text, $utf8Bom)

Write-Output "Temp: $tmpFile"

try {
    & $tmpFile -Version 'v1.3' -ProductName 'LingShu'
    $ok = $true
} finally {
    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
}

$releaseDir = Join-Path $projectRoot "release"
$output = Join-Path $releaseDir "LingShu-v1.3.exe"

if (Test-Path $output) {
    $hash = Get-FileHash -LiteralPath $output -Algorithm SHA256
    $sizeMb = [Math]::Round((Get-Item -LiteralPath $output).Length / 1MB, 2)
    $sw.Stop()
    Write-Output ""
    Write-Output "========================================"
    Write-Output " OUTPUT : $output"
    Write-Output " SIZE   : ${sizeMb}MB"
    Write-Output " SHA256 : $($hash.Hash)"
    Write-Output " TIME   : $([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
    Write-Output "========================================"
} else {
    Write-Output "ERROR: Build output not found"
}
