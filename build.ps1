[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$sourcePath = Join-Path $PSScriptRoot 'OrganizeDesktop.cs'
$iconPath = Join-Path $PSScriptRoot 'assets\desktop-organizer.ico'

foreach ($requiredFile in @($sourcePath, $iconPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required build file is missing: $requiredFile"
    }
}

$compilerCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$compiler = $compilerCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

if (-not $compiler) {
    throw 'The .NET Framework 4.x C# compiler was not found. Enable .NET Framework 4.x in Windows Features and try again.'
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$outputPath = Join-Path $OutputDirectory 'DesktopOrganizer.exe'

Write-Host "Compiler: $compiler"
& $compiler /nologo /target:winexe /platform:anycpu "/win32icon:$iconPath" "/out:$outputPath" /r:System.Windows.Forms.dll $sourcePath

if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "Build failed. Compiler exit code: $LASTEXITCODE"
}

$artifact = Get-Item -LiteralPath $outputPath
$hash = Get-FileHash -LiteralPath $outputPath -Algorithm SHA256
Write-Host "Build succeeded: $($artifact.FullName)"
Write-Host "File size: $($artifact.Length) bytes"
Write-Host "SHA-256: $($hash.Hash)"
