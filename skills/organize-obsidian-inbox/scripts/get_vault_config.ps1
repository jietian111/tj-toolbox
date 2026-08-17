[CmdletBinding()]
param(
    [string]$ConfigRoot,
    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ConfigRoot)) {
    $userProfile = [Environment]::GetFolderPath('UserProfile')
    if ([string]::IsNullOrWhiteSpace($userProfile)) {
        throw 'Unable to resolve the current user profile directory.'
    }
    $ConfigRoot = Join-Path $userProfile '.codex\organize-obsidian-inbox'
}

$configFile = Join-Path $ConfigRoot 'settings.json'
$result = [ordered]@{
    Configured = $false
    ConfigFile = $configFile
    DefaultVault = $null
    Valid = $false
    Reason = 'Configuration file not found.'
}

if (Test-Path -LiteralPath $configFile -PathType Leaf) {
    try {
        $settings = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
        $configuredPath = [string]$settings.default_vault
        if ([string]::IsNullOrWhiteSpace($configuredPath)) {
            $result.Reason = 'default_vault is missing from the configuration.'
        } elseif (!(Test-Path -LiteralPath $configuredPath -PathType Container)) {
            $result.DefaultVault = $configuredPath
            $result.Reason = 'The configured vault path does not exist or is inaccessible.'
        } else {
            $resolvedVault = (Resolve-Path -LiteralPath $configuredPath).Path
            $result.DefaultVault = $resolvedVault
            if (!(Test-Path -LiteralPath (Join-Path $resolvedVault '.obsidian') -PathType Container)) {
                $result.Reason = 'The configured path is not an Obsidian vault because .obsidian is missing.'
            } else {
                $result.Configured = $true
                $result.Valid = $true
                $result.Reason = 'Configuration is valid.'
            }
        }
    } catch {
        $result.Reason = "Configuration could not be read: $($_.Exception.Message)"
    }
}

$output = [pscustomobject]$result
if ($AsJson) {
    $output | ConvertTo-Json -Depth 3
} else {
    $output
}
