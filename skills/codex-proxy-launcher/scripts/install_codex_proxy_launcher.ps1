[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$ProxyPort,
    [string]$OutputDirectory,
    [string]$ShortcutPath
)

$ErrorActionPreference = 'Stop'

if (-not $PSBoundParameters.ContainsKey('ProxyPort')) {
    do {
        $rawPort = Read-Host 'Enter the local HTTP proxy port (for example, 7897)'
        $parsedPort = 0
        $validPort = [int]::TryParse($rawPort, [ref]$parsedPort) -and $parsedPort -ge 1 -and $parsedPort -le 65535
        if (-not $validPort) { Write-Warning 'Enter an integer from 1 through 65535.' }
    } until ($validPort)
    $ProxyPort = $parsedPort
}

$desktopPath = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $desktopPath 'Codex Proxy Launcher'
}
if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
    $ShortcutPath = Join-Path $desktopPath 'Codex.lnk'
}

$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$ShortcutPath = [IO.Path]::GetFullPath($ShortcutPath)
$shortcutParent = Split-Path -Parent $ShortcutPath
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
if ($shortcutParent) { New-Item -ItemType Directory -Path $shortcutParent -Force | Out-Null }

$skillDirectory = Split-Path $PSScriptRoot -Parent
$templatePath = Join-Path $skillDirectory 'assets\CodexProxyLauncher.cmd.template'
$resolverSource = Join-Path $skillDirectory 'assets\Resolve-CodexApp.ps1'
$launcherPath = Join-Path $OutputDirectory 'CodexProxyLauncher.cmd'
$resolverPath = Join-Path $OutputDirectory 'Resolve-CodexApp.ps1'

$template = Get-Content -LiteralPath $templatePath -Raw
$launcher = $template.Replace('__PROXY_PORT__', [string]$ProxyPort).Replace('__SHORTCUT_PATH__', $ShortcutPath)
Set-Content -LiteralPath $launcherPath -Value $launcher -Encoding ASCII
Copy-Item -LiteralPath $resolverSource -Destination $resolverPath -Force

$appPath = & $resolverPath
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $OutputDirectory
$shortcut.Description = "Launch Codex through http://127.0.0.1:$ProxyPort"
$shortcut.IconLocation = if ($appPath) { "$appPath,0" } else { "$env:SystemRoot\System32\shell32.dll,18" }
$shortcut.Save()

$checkOutput = & cmd.exe /d /c "`"$launcherPath`" --check"
$portState = ($checkOutput | Where-Object { $_ -like 'ProxyPort=*' } | Select-Object -First 1) -replace '^ProxyPort=', ''

[pscustomobject]@{
    ProxyUrl = "http://127.0.0.1:$ProxyPort"
    ProxyPortState = $portState
    AppPath = $appPath
    LauncherPath = $launcherPath
    ResolverPath = $resolverPath
    ShortcutPath = $ShortcutPath
    LauncherExists = Test-Path -LiteralPath $launcherPath
    ResolverExists = Test-Path -LiteralPath $resolverPath
    ShortcutExists = Test-Path -LiteralPath $ShortcutPath
}
