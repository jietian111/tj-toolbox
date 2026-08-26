$ErrorActionPreference = 'SilentlyContinue'

function Add-Candidate {
    param([System.Collections.Generic.List[string]]$List, [string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    if ($Path -match '\\app\\resources\\codex(?:\.exe)?$') {
        $appDirectory = Split-Path (Split-Path $Path -Parent) -Parent
        foreach ($name in @('ChatGPT.exe', 'Codex.exe')) {
            $List.Add((Join-Path $appDirectory $name))
        }
        return
    }
    $List.Add($Path)
}

function Add-Package {
    param([System.Collections.Generic.List[string]]$List, [object]$Package)
    if (-not $Package) { return }

    $manifestPath = Join-Path $Package.InstallLocation 'AppxManifest.xml'
    if (Test-Path -LiteralPath $manifestPath) {
        try {
            [xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw
            $executable = (@($manifest.Package.Applications.Application) | Select-Object -First 1).Executable
            if ($executable) {
                Add-Candidate $List (Join-Path $Package.InstallLocation ($executable -replace '/', '\'))
            }
        } catch {
        }
    }

    foreach ($name in @('ChatGPT.exe', 'Codex.exe')) {
        Add-Candidate $List (Join-Path $Package.InstallLocation "app\$name")
    }
}

$candidates = [System.Collections.Generic.List[string]]::new()
$packages = @()
$packages += Get-AppxPackage -Name OpenAI.Codex
$packages += Get-AppxPackage -Name OpenAI.ChatGPT
$packages += Get-AppxPackage | Where-Object {
    $_.Name -match 'OpenAI|ChatGPT|Codex' -or $_.PackageFullName -match 'OpenAI|ChatGPT|Codex'
}

$packages | Where-Object { $_ } | Sort-Object Version -Descending -Unique | ForEach-Object {
    Add-Package $candidates $_
}

foreach ($name in @('ChatGPT', 'Codex', 'codex')) {
    Get-Process -Name $name | ForEach-Object { Add-Candidate $candidates $_.Path }
}

$command = Get-Command codex
if ($command) { Add-Candidate $candidates $command.Source }

$candidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -Unique -First 1
