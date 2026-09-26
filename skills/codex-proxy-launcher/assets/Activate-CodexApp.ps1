param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [Parameter(Mandatory = $true)][string]$ProxyUrl,
    [switch]$ResolveOnly
)

$ErrorActionPreference = 'Stop'
$resolvedAppPath = [IO.Path]::GetFullPath($AppPath)
$appId = $null

$packages = @(
    Get-AppxPackage -Name OpenAI.Codex -ErrorAction SilentlyContinue
    Get-AppxPackage -Name OpenAI.ChatGPT -ErrorAction SilentlyContinue
) | Where-Object { $_ } | Sort-Object Version -Descending

foreach ($package in $packages) {
    $manifestPath = Join-Path $package.InstallLocation 'AppxManifest.xml'
    if (-not (Test-Path -LiteralPath $manifestPath)) { continue }
    [xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw

    foreach ($application in @($manifest.Package.Applications.Application)) {
        if (-not $application.Executable) { continue }
        $candidatePath = [IO.Path]::GetFullPath(
            (Join-Path $package.InstallLocation ($application.Executable -replace '/', '\'))
        )
        if ([string]::Equals($candidatePath, $resolvedAppPath, [StringComparison]::OrdinalIgnoreCase)) {
            $appId = "$($package.PackageFamilyName)!$($application.Id)"
            break
        }
    }
    if ($appId) { break }
}

if (-not $appId) {
    throw "No registered AppX application matches $resolvedAppPath"
}
if ($ResolveOnly) {
    "AppUserModelID=$appId"
    return
}

$activationApi = @'
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IApplicationActivationManager
{
    [PreserveSig]
    int ActivateApplication(
        [MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
        [MarshalAs(UnmanagedType.LPWStr)] string arguments,
        uint options,
        out uint processId);
}

public static class PackagedAppActivation
{
    public static uint Activate(string appUserModelId, string arguments)
    {
        var type = Type.GetTypeFromCLSID(new Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C"));
        var manager = (IApplicationActivationManager)Activator.CreateInstance(type);
        try
        {
            uint processId;
            int result = manager.ActivateApplication(appUserModelId, arguments, 0, out processId);
            if (result < 0) Marshal.ThrowExceptionForHR(result);
            return processId;
        }
        finally
        {
            Marshal.ReleaseComObject(manager);
        }
    }
}
'@

Add-Type -TypeDefinition $activationApi
$arguments = "--lang=zh-CN --proxy-server=`"$ProxyUrl`" --proxy-bypass-list=`"localhost;127.0.0.1;::1`""
$pidValue = [PackagedAppActivation]::Activate($appId, $arguments)
"ActivatedPid=$pidValue"
