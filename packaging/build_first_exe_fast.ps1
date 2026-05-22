﻿param(
    [string]$Version = "v1.0.0",
    [string]$ProductName = "灵枢",
    [string]$ReuseRuntimeFrom = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$ReleaseRoot = Join-Path $ProjectRoot "release"
$AppIconSource = Join-Path $ProjectRoot "packaging\app_icon.ico"
$LauncherSource = Join-Path $ProjectRoot "packaging\Launcher.cs"
$StartupSplashImage = Join-Path $ProjectRoot "novel_app\qt\assets\startup_anime.jpg"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$RequirementsHash = (Get-FileHash -LiteralPath $RequirementsFile -Algorithm SHA256).Hash

if (-not (Test-Path -LiteralPath $StartupSplashImage)) {
    throw "Startup splash image not found: $StartupSplashImage"
}

$BuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) "$ProductName-release-build"
$PayloadRoot = Join-Path $BuildRoot "payload"
$PayloadApp = Join-Path $PayloadRoot "app"
$PayloadPython = Join-Path $PayloadRoot "python"
$IExpressRoot = Join-Path $BuildRoot "iexpress"
$PayloadZip = Join-Path $IExpressRoot "app.zip"
$TempOutputExe = Join-Path $BuildRoot "$ProductName-$Version.exe"
$OutputExe = Join-Path $ReleaseRoot "$ProductName-$Version.exe"
$LauncherConfig = Join-Path $BuildRoot "LauncherConfig.cs"
$CscWorkRoot = Join-Path ([System.IO.Path]::GetTempPath()) "lingshu-csc-$([System.Guid]::NewGuid().ToString('N').Substring(0, 8))"

$AppExcludeDirs = @("__pycache__", "tests", "docs", ".git", ".pytest_cache", ".mypy_cache", "star_graph_enhancement", "codex_skills")

function Reset-Directory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Copy-DirectoryFast([string]$Source, [string]$Destination, [string[]]$ExcludeDirs = @()) {
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Source directory not found: $Source"
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $xdArgs = @()
    foreach ($dir in $ExcludeDirs) {
        $xdArgs += "/XD"
        $xdArgs += $dir
    }
    $xfArgs = @("/XF", "*.pyc", "*.pyo")
    $result = robocopy $Source $Destination /E /MT:8 /NJH /NJS /NP /NS /NDL /R:1 /W:1 @xdArgs @xfArgs
    $exitCode = $LASTEXITCODE
    if ($exitCode -ge 8) {
        throw "robocopy failed with exit code $exitCode"
    }
}

function Resolve-PythonRuntimeRoot([string]$PythonExePath) {
    $code = "import sys; print(sys.base_prefix or sys.prefix)"
    $runtimeRoot = (& $PythonExePath -c $code 2>$null | Select-Object -First 1)
    if (-not $runtimeRoot) {
        $runtimeRoot = Split-Path -Parent $PythonExePath
    }
    $runtimeRoot = $runtimeRoot.Trim()
    if (-not (Test-Path -LiteralPath $runtimeRoot)) {
        throw "Could not resolve Python runtime root from $PythonExePath"
    }
    return (Resolve-Path -LiteralPath $runtimeRoot).Path
}

function Copy-FileIfExists([string]$Source, [string]$DestinationDir, [bool]$Required = $true) {
    if (Test-Path -LiteralPath $Source) {
        Copy-Item -LiteralPath $Source -Destination $DestinationDir -Force
        return
    }
    if ($Required) {
        throw "Required runtime file not found: $Source"
    }
    Write-Warning "  Optional runtime file not found: $Source"
}

function Clear-DirectoryContents([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        return
    }
    Get-ChildItem -LiteralPath $Path -Force | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }
}

function Copy-RuntimeFromSystem([string]$PythonExePath) {
    $PythonRoot = Resolve-PythonRuntimeRoot $PythonExePath
    Copy-FileIfExists (Join-Path $PythonRoot "python.exe") $PayloadPython
    Copy-FileIfExists (Join-Path $PythonRoot "pythonw.exe") $PayloadPython
    Copy-FileIfExists (Join-Path $PythonRoot "python3.dll") $PayloadPython $false
    $PythonDll = Get-ChildItem -Path $PythonRoot -Filter "python3*.dll" |
        Where-Object { $_.Name -match "^python3\d+\.dll$" } |
        Select-Object -First 1
    if (-not $PythonDll) {
        throw "Could not find python3*.dll in $PythonRoot"
    }
    Copy-Item -LiteralPath $PythonDll.FullName -Destination $PayloadPython -Force
    Write-Output "  Copied Python DLL: $($PythonDll.Name)"
    Copy-FileIfExists (Join-Path $PythonRoot "vcruntime140.dll") $PayloadPython $false
    Copy-FileIfExists (Join-Path $PythonRoot "vcruntime140_1.dll") $PayloadPython $false
    Copy-DirectoryFast (Join-Path $PythonRoot "DLLs") (Join-Path $PayloadPython "DLLs")
    Copy-DirectoryFast (Join-Path $PythonRoot "Lib") (Join-Path $PayloadPython "Lib") @("__pycache__")
    $TclSource = Join-Path $PythonRoot "tcl"
    if (Test-Path -LiteralPath $TclSource) {
        Copy-DirectoryFast $TclSource (Join-Path $PayloadPython "tcl") @("__pycache__")
    }
}

function Save-RuntimeCache([string]$PayloadDir, [string]$CacheName, [string]$RequirementsHashValue) {
    $RuntimeCacheRoot = Join-Path $ReleaseRoot "runtime"
    $CacheDir = Join-Path $RuntimeCacheRoot $CacheName
    if (Test-Path -LiteralPath $CacheDir) {
        Remove-Item -LiteralPath $CacheDir -Recurse -Force
    }
    $CachePythonDir = Join-Path $CacheDir "python"
    robocopy $PayloadDir $CachePythonDir /E /MT:8 /NJH /NJS /NP /NS /NDL /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy save-runtime failed with exit code $LASTEXITCODE" }
    @{
        requirements_hash = $RequirementsHashValue
        created_at = [DateTime]::UtcNow.ToString("O")
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $CacheDir "runtime-manifest.json") -Encoding UTF8
    Write-Output "  Runtime cached to runtime/$CacheName/"
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()

Write-Output "[0/6] Cleaning previous build caches..."
$TempRoot = [System.IO.Path]::GetTempPath()
Get-ChildItem -LiteralPath $TempRoot -Directory -Filter "*release-build" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        [System.IO.Directory]::Delete($_.FullName, $true)
    } catch {
        Write-Warning "  Could not clean $($_.Name) (may be locked), continuing."
    }
}
if (Test-Path -LiteralPath $BuildRoot) {
    try { [System.IO.Directory]::Delete($BuildRoot, $true) } catch { }
    if (Test-Path -LiteralPath $BuildRoot) {
        $BuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) "$ProductName-$Version-$([System.Guid]::NewGuid().ToString('N').Substring(0,8))"
        $PayloadRoot = Join-Path $BuildRoot "payload"
        $PayloadApp = Join-Path $PayloadRoot "app"
        $PayloadPython = Join-Path $PayloadRoot "python"
        $IExpressRoot = Join-Path $BuildRoot "iexpress"
        $PayloadZip = Join-Path $IExpressRoot "app.zip"
        $TempOutputExe = Join-Path $BuildRoot "$ProductName-$Version.exe"
        Write-Output "  Build root locked, using: $BuildRoot"
    }
}
[System.IO.Directory]::CreateDirectory($BuildRoot)
[System.IO.Directory]::CreateDirectory($ReleaseRoot)
[System.IO.Directory]::CreateDirectory($PayloadRoot)
[System.IO.Directory]::CreateDirectory($PayloadApp)
[System.IO.Directory]::CreateDirectory($PayloadPython)
[System.IO.Directory]::CreateDirectory($IExpressRoot)
Write-Output "  Cache cleaned"

Write-Output "[1/6] Copying app code..."
Copy-Item -LiteralPath (Join-Path $ProjectRoot "main.py") -Destination $PayloadApp -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "requirements.txt") -Destination $PayloadApp -Force
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "README.md")) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $PayloadApp -Force
}
Copy-DirectoryFast (Join-Path $ProjectRoot "novel_app") (Join-Path $PayloadApp "novel_app") $AppExcludeDirs
$VendorSource = Join-Path $ProjectRoot "vendor"
if (Test-Path -LiteralPath $VendorSource) {
    Copy-DirectoryFast $VendorSource (Join-Path $PayloadApp "vendor") @("__pycache__")
}
$t1 = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
Write-Output "  App code done (${t1}s)"

if (Test-Path -LiteralPath $AppIconSource) {
    Write-Output "[2/6] Embedding app icon into payload..."
    $PayloadPackagingDir = Join-Path $PayloadApp "packaging"
    New-Item -ItemType Directory -Path $PayloadPackagingDir -Force | Out-Null
    Copy-Item -LiteralPath $AppIconSource -Destination $PayloadPackagingDir -Force
    $t2 = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
    Write-Output "  Icon embedded (${t2}s)"
} else {
    Write-Warning "[2/6] App icon not found at $AppIconSource, skipping."
}

$RuntimeRepo = Join-Path $ReleaseRoot "runtime"
$runtimeSourcePath = ""
$runtimeNeedsCaching = $false
$runtimeInstallDependencies = $false
$runtimeCacheName = "$Version-$($RequirementsHash.Substring(0, 8).ToLowerInvariant())"

function Test-RuntimeCacheUsable([string]$CacheDir) {
    if (-not $CacheDir) { return $false }
    return (Test-Path -LiteralPath (Join-Path $CacheDir "python\python.exe"))
}

function Test-RuntimeCacheMatches([string]$CacheDir) {
    if (-not (Test-RuntimeCacheUsable $CacheDir)) { return $false }
    $manifestPath = Join-Path $CacheDir "runtime-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) { return $false }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        return [string]$manifest.requirements_hash -eq $RequirementsHash
    } catch {
        return $false
    }
}

function Resolve-RuntimeCacheDir([string]$CacheName) {
    if (-not $CacheName) { return $null }
    $names = New-Object System.Collections.Generic.List[string]
    $names.Add($CacheName)
    if ($CacheName.EndsWith(".exe", [StringComparison]::OrdinalIgnoreCase)) {
        $names.Add([System.IO.Path]::GetFileNameWithoutExtension($CacheName))
    }
    $productPrefix = "$ProductName-"
    if ($CacheName.StartsWith($productPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        $names.Add($CacheName.Substring($productPrefix.Length))
    }
    foreach ($name in $names | Select-Object -Unique) {
        $dir = Join-Path $RuntimeRepo $name
        if (Test-Path -LiteralPath $dir) {
            return $dir
        }
    }
    return (Join-Path $RuntimeRepo $CacheName)
}

function Find-LatestRuntime {
    if (-not (Test-Path $RuntimeRepo)) { return $null }
    $dirs = Get-ChildItem $RuntimeRepo -Directory | Where-Object { Test-RuntimeCacheMatches $_.FullName }
    if (-not $dirs) { return $null }
    return ($dirs | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
}

if ($ReuseRuntimeFrom) {
    $runtimeCacheDir = Resolve-RuntimeCacheDir $ReuseRuntimeFrom
    if (Test-RuntimeCacheUsable $runtimeCacheDir) {
        $runtimeSourcePath = Join-Path $runtimeCacheDir "python"
        $cacheDisplayName = Split-Path -Leaf $runtimeCacheDir
        Write-Output "[*] Reusing requested runtime from runtime/$cacheDisplayName/"
        if (-not (Test-RuntimeCacheMatches $runtimeCacheDir)) {
            Write-Warning "Requested runtime cache has no matching manifest; it will be reused and dependencies will be refreshed in the payload."
            $runtimeInstallDependencies = $true
        }
    } else {
        Write-Warning "Runtime source not found: $runtimeCacheDir, fallback to latest."
        $runtimeSourcePath = ""
    }
}

if (-not $runtimeSourcePath) {
    $latest = Find-LatestRuntime
    if ($latest) {
        $runtimeSourcePath = Join-Path (Join-Path $RuntimeRepo $latest) "python"
        Write-Output "[*] Auto-reusing runtime from runtime/$latest/"
    }
}

$PythonExe = $null
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = (Get-Command python.exe).Source
}
$PythonRoot = Resolve-PythonRuntimeRoot $PythonExe
Write-Output "  Build Python: $PythonExe"
Write-Output "  Runtime root: $PythonRoot"

if ($runtimeSourcePath) {
    Write-Output "[3/6] Reusing Python runtime from $runtimeSourcePath..."
    robocopy $runtimeSourcePath $PayloadPython /E /MT:8 /NJH /NJS /NP /NS /NDL /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy runtime-reuse failed with exit code $LASTEXITCODE" }
    $t3 = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
    Write-Output "  Python runtime reused (${t3}s)"
} else {
    Write-Output "[3/6] Copying Python runtime from system Python..."
    if (Test-Path -LiteralPath $VenvPython) {
        Write-Output "  Using Python from project .venv"
    }
    Copy-RuntimeFromSystem $PythonExe
    $runtimeNeedsCaching = $true
    $t3 = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
    Write-Output "  Python runtime done (${t3}s)"
}

Write-Output "[4/6] Installing dependencies..."
$PayloadSitePackages = Join-Path $PayloadPython "Lib\site-packages"
if ($runtimeSourcePath -and -not $runtimeInstallDependencies) {
    Write-Output "  Runtime reused, dependencies already present, skipping install"
} else {
    New-Item -ItemType Directory -Path $PayloadSitePackages -Force | Out-Null
    if (-not $runtimeSourcePath) {
        Clear-DirectoryContents $PayloadSitePackages
    } else {
        Write-Output "  Refreshing dependencies on top of requested runtime cache"
    }
    $pipArgs = @(
        "--disable-pip-version-check",
        "--no-compile",
        "--no-cache-dir",
        "--target", $PayloadSitePackages,
        "-r", $RequirementsFile
    )
    if ($runtimeInstallDependencies) {
        $pipArgs += "--upgrade"
    }
    & $PythonExe -m pip install @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed with exit code $LASTEXITCODE"
    }
    Write-Output "  Dependencies installed to payload site-packages"
}
$t4 = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
Write-Output "  Dependencies done (${t4}s)"

Write-Output "[5/6] Compressing payload..."
Add-Type -AssemblyName "System.IO.Compression.FileSystem"
$compressionOpt = [System.IO.Compression.CompressionLevel]::Fastest
if (Test-Path -LiteralPath $PayloadZip) {
    Remove-Item -LiteralPath $PayloadZip -Force
}
[System.IO.Compression.ZipFile]::CreateFromDirectory($PayloadRoot, $PayloadZip, $compressionOpt, $false)
$t5 = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
Write-Output "  Compression done (${t5}s)"

if ($runtimeNeedsCaching) {
    Write-Output "[*] Saving runtime cache for future fast builds..."
    Save-RuntimeCache $PayloadPython $runtimeCacheName $RequirementsHash
}

$EscapedProductName = $ProductName.Replace("\", "\\").Replace('"', '\"')
$EscapedVersion = $Version.Replace("\", "\\").Replace('"', '\"')
@"
namespace SimpleAINovelAppLauncher
{
    internal static class LauncherConfig
    {
        public const string AppName = "$EscapedProductName";
        public const string Version = "$EscapedVersion";
    }
}
"@ | Set-Content -LiteralPath $LauncherConfig -Encoding UTF8

$CscCandidates = @(
    (Join-Path $env:SystemRoot "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:SystemRoot "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Csc = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Csc) {
    throw "Could not find .NET Framework csc.exe"
}

Write-Output "[6/6] Compiling C# launcher..."
Reset-Directory $CscWorkRoot
$CscLauncherSource = Join-Path $CscWorkRoot "Launcher.cs"
$CscLauncherConfig = Join-Path $CscWorkRoot "LauncherConfig.cs"
$CscPayloadZip = Join-Path $CscWorkRoot "payload.zip"
$CscSplashImage = Join-Path $CscWorkRoot "startup_anime.jpg"
$CscTempOutputExe = Join-Path $CscWorkRoot "launcher.exe"
Copy-Item -LiteralPath $LauncherSource -Destination $CscLauncherSource -Force
Copy-Item -LiteralPath $LauncherConfig -Destination $CscLauncherConfig -Force
Copy-Item -LiteralPath $PayloadZip -Destination $CscPayloadZip -Force
Copy-Item -LiteralPath $StartupSplashImage -Destination $CscSplashImage -Force

$cscArgs = @(
    "/nologo",
    "/target:winexe",
    "/optimize+",
    "/out:$CscTempOutputExe",
    "/resource:$CscPayloadZip,payload.zip",
    "/resource:$CscSplashImage,startup_anime.jpg",
    "/reference:System.IO.Compression.dll",
    "/reference:System.IO.Compression.FileSystem.dll",
    "/reference:System.Drawing.dll",
    "/reference:System.Windows.Forms.dll"
)
if (Test-Path -LiteralPath $AppIconSource) {
    $CscAppIcon = Join-Path $CscWorkRoot "app_icon.ico"
    Copy-Item -LiteralPath $AppIconSource -Destination $CscAppIcon -Force
    $cscArgs += "/win32icon:$CscAppIcon"
}
$cscArgs += $CscLauncherSource
$cscArgs += $CscLauncherConfig
& $Csc @cscArgs

if (-not (Test-Path -LiteralPath $CscTempOutputExe)) {
    throw "Launcher compiler did not create $CscTempOutputExe"
}

Copy-Item -LiteralPath $CscTempOutputExe -Destination $TempOutputExe -Force
Copy-Item -LiteralPath $TempOutputExe -Destination $OutputExe -Force
try {
    Remove-Item -LiteralPath $CscWorkRoot -Recurse -Force
} catch {
    Write-Warning "Could not clean C# work directory: $CscWorkRoot"
}
$sw.Stop()

$Hash = Get-FileHash -LiteralPath $OutputExe -Algorithm SHA256
$SizeMb = [Math]::Round((Get-Item -LiteralPath $OutputExe).Length / 1MB, 2)
Write-Output ""
Write-Output "=============================="
Write-Output "  Product : $ProductName"
Write-Output "  Version : $Version"
Write-Output "  Built   : $OutputExe"
Write-Output "  Size    : ${SizeMb}MB"
Write-Output "  SHA256  : $($Hash.Hash)"
Write-Output "  Elapsed : $([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
Write-Output "=============================="
