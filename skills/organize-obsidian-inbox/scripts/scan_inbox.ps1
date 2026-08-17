[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$VaultPath,

    [switch]$AsJson,

    [switch]$IncludeSystemNotes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$vaultRoot = (Resolve-Path -LiteralPath $VaultPath).Path
$vaultItem = Get-Item -LiteralPath $vaultRoot
if (!$vaultItem.PSIsContainer) {
    throw "VaultPath is not a directory: $vaultRoot"
}

$obsidianPath = Join-Path $vaultRoot '.obsidian'
$inboxPath = Join-Path $vaultRoot '00-待整理'
$recordPath = Join-Path $vaultRoot '99-系统\资料处理记录.md'

if (!(Test-Path -LiteralPath $obsidianPath -PathType Container)) {
    throw "Not an Obsidian vault: $vaultRoot"
}
if (!(Test-Path -LiteralPath $inboxPath -PathType Container)) {
    throw "Inbox not found: $inboxPath"
}

$recordText = if (Test-Path -LiteralPath $recordPath -PathType Leaf) {
    Get-Content -LiteralPath $recordPath -Raw
} else {
    ''
}

$supportedExtensions = @('.md', '.txt', '.html', '.htm', '.mhtml', '.pdf', '.docx', '.ppt', '.pptx', '.jpg', '.jpeg', '.png')
$candidateFiles = Get-ChildItem -LiteralPath $inboxPath -Recurse -Force -File |
    Where-Object {
        $IncludeSystemNotes -or $_.Name -ne '待整理说明.md'
    } |
    Sort-Object FullName

$scanResults = foreach ($candidateFile in $candidateFiles) {
    $sha256 = (Get-FileHash -LiteralPath $candidateFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $relativePath = [System.IO.Path]::GetRelativePath($vaultRoot, $candidateFile.FullName).Replace('\', '/')
    $extension = $candidateFile.Extension.ToLowerInvariant()

    $status = if ($recordText.IndexOf($sha256, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        'Processed'
    } elseif ($supportedExtensions -contains $extension) {
        'New'
    } else {
        'Unsupported'
    }

    [pscustomobject]@{
        Status = $status
        Source = $relativePath
        Extension = $extension
        SizeBytes = $candidateFile.Length
        LastWriteTime = $candidateFile.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
        Sha256 = $sha256
    }
}

if ($AsJson) {
    ConvertTo-Json -InputObject @($scanResults) -Depth 3
} else {
    $scanResults
}
