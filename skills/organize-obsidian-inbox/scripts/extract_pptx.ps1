[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [switch]$AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedPath = (Resolve-Path -LiteralPath $FilePath).Path
$fileItem = Get-Item -LiteralPath $resolvedPath
if ($fileItem.PSIsContainer -or $fileItem.Extension.ToLowerInvariant() -ne '.pptx') {
    throw "FilePath must point to a PPTX file: $resolvedPath"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedPath)

function Get-ZipEntryText {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryPath
    )

    $entry = $Archive.GetEntry($EntryPath)
    if ($null -eq $entry) { return $null }
    $reader = New-Object System.IO.StreamReader($entry.Open())
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}

function Resolve-ZipTarget {
    param(
        [string]$BaseEntry,
        [string]$RelativeTarget
    )

    $baseUri = [System.Uri]::new("https://zip.local/$BaseEntry")
    $targetUri = [System.Uri]::new($baseUri, $RelativeTarget)
    return $targetUri.AbsolutePath.TrimStart('/')
}

function Get-TextNodes {
    param([string]$XmlText)

    if ([string]::IsNullOrWhiteSpace($XmlText)) { return @() }
    $document = New-Object System.Xml.XmlDocument
    $document.PreserveWhitespace = $false
    $document.LoadXml($XmlText)
    $namespaceManager = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespaceManager.AddNamespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
    return @(
        $document.SelectNodes('//a:t', $namespaceManager) |
            ForEach-Object { $_.InnerText.Trim() } |
            Where-Object { $_ }
    )
}

try {
    $presentationXml = Get-ZipEntryText -Archive $archive -EntryPath 'ppt/presentation.xml'
    $presentationRelsXml = Get-ZipEntryText -Archive $archive -EntryPath 'ppt/_rels/presentation.xml.rels'
    if (!$presentationXml -or !$presentationRelsXml) {
        throw 'The PPTX package is missing presentation metadata.'
    }

    $presentationDocument = New-Object System.Xml.XmlDocument
    $presentationDocument.LoadXml($presentationXml)
    $presentationNamespaces = New-Object System.Xml.XmlNamespaceManager($presentationDocument.NameTable)
    $presentationNamespaces.AddNamespace('p', 'http://schemas.openxmlformats.org/presentationml/2006/main')
    $presentationNamespaces.AddNamespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')

    $relsDocument = New-Object System.Xml.XmlDocument
    $relsDocument.LoadXml($presentationRelsXml)
    $relsNamespaces = New-Object System.Xml.XmlNamespaceManager($relsDocument.NameTable)
    $relsNamespaces.AddNamespace('rel', 'http://schemas.openxmlformats.org/package/2006/relationships')

    $relationshipTargets = @{}
    foreach ($relationship in $relsDocument.SelectNodes('//rel:Relationship', $relsNamespaces)) {
        $relationshipTargets[$relationship.Id] = $relationship.Target
    }

    $slideResults = @()
    $slideNumber = 0
    foreach ($slideId in $presentationDocument.SelectNodes('//p:sldIdLst/p:sldId', $presentationNamespaces)) {
        $slideNumber++
        $relationshipId = $slideId.GetAttribute('id', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
        if (!$relationshipTargets.ContainsKey($relationshipId)) {
            throw "Slide relationship not found: $relationshipId"
        }

        $slideEntryPath = Resolve-ZipTarget -BaseEntry 'ppt/presentation.xml' -RelativeTarget $relationshipTargets[$relationshipId]
        $slideXml = Get-ZipEntryText -Archive $archive -EntryPath $slideEntryPath
        $slideText = @(Get-TextNodes -XmlText $slideXml)

        $slideFileName = [System.IO.Path]::GetFileName($slideEntryPath)
        $slideDirectory = [System.IO.Path]::GetDirectoryName($slideEntryPath).Replace('\', '/')
        $slideRelsPath = "$slideDirectory/_rels/$slideFileName.rels"
        $slideRelsXml = Get-ZipEntryText -Archive $archive -EntryPath $slideRelsPath
        $notesText = @()

        if ($slideRelsXml) {
            $slideRelsDocument = New-Object System.Xml.XmlDocument
            $slideRelsDocument.LoadXml($slideRelsXml)
            $slideRelsNamespaces = New-Object System.Xml.XmlNamespaceManager($slideRelsDocument.NameTable)
            $slideRelsNamespaces.AddNamespace('rel', 'http://schemas.openxmlformats.org/package/2006/relationships')
            $notesRelationship = $slideRelsDocument.SelectSingleNode("//rel:Relationship[contains(@Type, '/notesSlide')]", $slideRelsNamespaces)
            if ($notesRelationship) {
                $notesEntryPath = Resolve-ZipTarget -BaseEntry $slideEntryPath -RelativeTarget $notesRelationship.Target
                $notesXml = Get-ZipEntryText -Archive $archive -EntryPath $notesEntryPath
                $notesText = @(Get-TextNodes -XmlText $notesXml)
            }
        }

        $slideResults += [pscustomobject]@{
            SlideNumber = $slideNumber
            Text = $slideText
            SpeakerNotes = $notesText
        }
    }

    $result = [pscustomobject]@{
        File = $resolvedPath
        Sha256 = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash.ToLowerInvariant()
        SlideCount = $slideResults.Count
        Slides = $slideResults
    }

    if ($AsJson) {
        $result | ConvertTo-Json -Depth 6
    } else {
        $result
    }
} finally {
    $archive.Dispose()
}
