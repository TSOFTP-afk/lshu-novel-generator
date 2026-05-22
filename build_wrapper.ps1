$ErrorActionPreference = "Stop"
$scriptPath = "F:\项目\灵枢\packaging\build_first_exe_fast.ps1"
$Version = "v1.3"
$ProductName = "灵枢"
$ReuseRuntimeFrom = "v1.3预览版"
& $scriptPath -Version $Version -ProductName $ProductName -ReuseRuntimeFrom $ReuseRuntimeFrom
