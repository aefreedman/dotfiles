$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') { throw 'Windows only' }
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
    foreach ($font in $fonts) {
        $target = Join-Path $destination $font.Name
        $same = (Test-Path $target) -and ((Get-FileHash $target).Hash -eq (Get-FileHash $font.FullName).Hash)
        if (-not $same) { Copy-Item -LiteralPath $font.FullName -Destination $target -Force }
        $style = $font.BaseName -replace '^JetBrainsMono-', ''
        New-ItemProperty -Path $registry -Name ("JetBrains Mono " + $style + " (TrueType)") -Value $target -PropertyType String -Force | Out-Null
        if ([DotfilesFontRegistration]::AddFontResourceEx($target, 0, [IntPtr]::Zero) -eq 0) {
            throw "Windows could not register font $($font.Name)"
        }
    }
    Write-Output "Registered $($fonts.Count) JetBrains Mono fonts. Reopen apps to refresh font discovery."
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force
}
