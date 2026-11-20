param(
    [Parameter(Mandatory)]
    [ValidateSet('solarized-dark', 'solarized-light')]
    [string]$Theme
)

if (-not (Get-Command Set-PSReadLineOption -ErrorAction SilentlyContinue)) { return }

$variant = $Theme.Split('-')[1]
$palettePath = Join-Path $PSScriptRoot '../dotfiles/solarized.conf'
$palette = ConvertFrom-StringData (Get-Content -LiteralPath $palettePath -Raw -ErrorAction Stop)
$foreground = $palette["${variant}_foreground"]
$comment = $palette["${variant}_comment"]

Set-PSReadLineOption -Colors @{
    Default          = "#$foreground"
    Parameter        = "#$($palette.parameter)"
    Comment          = "#$comment"
    InlinePrediction = "#$comment"
    ListPrediction   = "#$comment"
    Command          = "#$($palette.identifier)"
    Variable         = "#$($palette.identifier)"
    Member           = "#$($palette.identifier)"
    Keyword          = "#$($palette.statement)"
    Operator         = "#$($palette.statement)"
    String           = "#$($palette.literal)"
    Number           = "#$($palette.literal)"
    Type             = "#$($palette.type)"
    Error            = "#$($palette.error)"
}
