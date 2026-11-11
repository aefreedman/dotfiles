param([switch]$Install)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $Install) {
    Write-Output 'Plan: install WinGet packages, fonts, Herdr app/core, Pi, and its shared packages.'
    Write-Output 'No changes made. Use -Install to install.'
    return
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install/update Microsoft App Installer to obtain WinGet first.' }
& winget import --import-file (Join-Path $root 'packages/windows-winget.json') --ignore-versions --disable-interactivity
if ($LASTEXITCODE) { throw "WinGet import failed ($LASTEXITCODE). Review package/source agreements in WinGet." }
# Refresh this process after installers add user/system PATH entries.
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv was not found after package installation.' }
& uv run --no-project --python 3.14 (Join-Path $root 'tools/provision.py') --install --skip-packages
if ($LASTEXITCODE) { throw "Provisioning failed ($LASTEXITCODE)" }
