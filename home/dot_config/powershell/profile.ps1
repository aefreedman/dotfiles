$theme = if ($env:DOTFILES_THEME) { $env:DOTFILES_THEME } else { 'solarized-dark' }
if ($theme -notin @('solarized-dark','solarized-light')) { throw 'DOTFILES_THEME must be solarized-dark or solarized-light' }
$themePath = Join-Path $HOME ".config/oh-my-posh/$theme.omp.json"
if (-not (Test-Path -LiteralPath $themePath)) { throw 'dotfiles: required Oh My Posh theme is missing' }
if (-not (Get-Command oh-my-posh -ErrorAction SilentlyContinue)) { throw 'dotfiles: oh-my-posh is missing; run the explicit bootstrap' }
oh-my-posh init pwsh --config $themePath | Invoke-Expression

function wezwk {
    param([string]$Path = (Get-Location).Path)
    if (-not $env:WEZTERM_PANE) { throw 'wezwk: run this command inside WezTerm' }
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).ProviderPath
    if (-not (Test-Path -LiteralPath $resolved -PathType Container)) { throw 'wezwk: target is not a directory' }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($resolved))
    [Console]::Write("$([char]27)]1337;SetUserVar=open_workspace=$encoded$([char]7)")
}

$localProfile = Join-Path $HOME '.config/dotfiles/local.ps1'
if (Test-Path -LiteralPath $localProfile) { . $localProfile }
