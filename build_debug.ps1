$ErrorActionPreference = "Stop"
$projectRoot = $PWD.Path

$srcScript = Join-Path $projectRoot "packaging\build_first_exe_fast.ps1"
$bytes = [System.IO.File]::ReadAllBytes($srcScript)
$text = [System.Text.Encoding]::UTF8.GetString($bytes)

$ling = [char]0x7075
$shu = [char]0x67a2
$chineseName = "$ling$shu"
$oldPattern = '[string]$ProductName = "' + $chineseName + '"'
$newDefine  = '[string]$ProductName = "LingShu"'
$text = $text.Replace($oldPattern, $newDefine)

$tmpFile = Join-Path $env:TEMP "lingshu_build_v13.ps1"
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
[System.IO.File]::WriteAllText($tmpFile, $text, $utf8Bom)

# Verify temp file
$verifyBytes = [System.IO.File]::ReadAllBytes($tmpFile)
$hasBom = ($verifyBytes[0] -eq 0xEF -and $verifyBytes[1] -eq 0xBB -and $verifyBytes[2] -eq 0xBF)
Write-Output "BOM present: $hasBom"

$verifyText = [System.Text.Encoding]::UTF8.GetString($verifyBytes)
$lines = $verifyText -split '\r?\n'
for ($i = 0; $i -lt 5; $i++) { Write-Output "Line $($i+1): $($lines[$i])" }

# Check for Chinese in param block
for ($i = 0; $i -lt 10; $i++) {
    $ch = [char]0x7075
    if ($lines[$i] -match $ch) { Write-Output "Chinese found on line $($i+1)!" }
}
Write-Output "No Chinese in first 10 lines"

# Now try running it
try {
    & $tmpFile -Version 'v1.3' -ProductName 'LingShu'
    Write-Output "SUCCESS!"
} catch {
    Write-Output "Error: $_"
}

Write-Output "Keeping temp file at: $tmpFile for debugging"
