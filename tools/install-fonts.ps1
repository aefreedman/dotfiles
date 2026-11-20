$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') { throw 'Windows only' }
$manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../packages/manifest.json') | ConvertFrom-Json
$release = Invoke-RestMethod 'https://api.github.com/repos/JetBrains/JetBrainsMono/releases/latest'
$assets = @($release.assets | Where-Object { $_.name -match '^JetBrainsMono-[0-9.]+\.zip$' })
if ($assets.Count -ne 1) { throw 'Expected one official JetBrains Mono release archive' }
$url = [string]$assets[0].browser_download_url
if (-not $url.StartsWith('https://github.com/JetBrains/JetBrainsMono/releases/download/')) { throw 'Unexpected font download source' }
$temp = Join-Path ([IO.Path]::GetTempPath()) ('dotfiles-fonts-' + [guid]::NewGuid())
New-Item -ItemType Directory $temp | Out-Null
try {
    $archive = Join-Path $temp 'fonts.zip'
    Invoke-WebRequest -Uri $url -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $temp 'unpacked')
    $fonts = @(Get-ChildItem (Join-Path $temp 'unpacked/fonts/ttf') -Filter 'JetBrainsMono-*.ttf')
    if ($fonts.Count -eq 0) { throw 'Official archive contains no expected original-family TTF fonts' }
    $destination = Join-Path $env:LOCALAPPDATA 'Microsoft/Windows/Fonts'
    New-Item -ItemType Directory -Force $destination | Out-Null
    $registry = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
    if (-not (Test-Path -LiteralPath $registry)) { New-Item -Path $registry -Force | Out-Null }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DotfilesFontRegistration {
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern int AddFontResourceEx(string path, uint flags, IntPtr reserved);
}
'@
    function Register-Font([IO.FileInfo]$font, [string]$name) {
        $target = Join-Path $destination $font.Name
        $same = (Test-Path -LiteralPath $target) -and ((Get-FileHash -LiteralPath $target).Hash -eq (Get-FileHash -LiteralPath $font.FullName).Hash)
        if (-not $same) { Copy-Item -LiteralPath $font.FullName -Destination $target -Force }
        $label = "$name (TrueType)"
        if ($same -and (Get-ItemProperty -LiteralPath $registry -ErrorAction Stop).$label -eq $target) { return }
        if ([DotfilesFontRegistration]::AddFontResourceEx($target, 0, [IntPtr]::Zero) -eq 0) {
            throw "Windows could not register font $($font.Name)"
        }
        New-ItemProperty -Path $registry -Name $label -Value $target -PropertyType String -Force | Out-Null
    }
    foreach ($font in $fonts) {
        $style = $font.BaseName -replace '^JetBrainsMono-', ''
        Register-Font $font "JetBrains Mono $style"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($bundle in $manifest.windows.fontArchives) {
        if ($bundle.url -notmatch '^https://github\.com/(be5invis/Iosevka|arrowtype/recursive)/releases/download/') {
            throw "Unexpected font download source for $($bundle.name)"
        }
        Write-Output "Downloading $($bundle.name)"
        Invoke-WebRequest -UseBasicParsing -Uri $bundle.url -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $bundle.sha256) {
            throw "Font archive checksum mismatch for $($bundle.name)"
        }
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            $entry = $zip.GetEntry($bundle.file)
            if (-not $entry) { throw "Expected font missing: $($bundle.file)" }
            $source = Join-Path $temp $entry.Name
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $source, $true)
            Register-Font (Get-Item -LiteralPath $source) $bundle.name
        } finally {
            $zip.Dispose()
        }
    }
    Write-Output 'Reopen apps to refresh font discovery.'
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force
}
