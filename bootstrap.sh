#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mode="${1:---diff}"
if [[ $# -gt 1 ]]; then
  printf 'Usage: %s [--diff|--sync|--install]\n' "$0" >&2
  exit 2
fi
case "$mode" in
  --diff|--sync|--install) ;;
  *) printf 'Usage: %s [--diff|--sync|--install]\n' "$0" >&2; exit 2 ;;
esac
if [[ "$(uname -s)" != "Darwin" ]]; then
  printf '%s\n' 'This bootstrap is for macOS. Use bootstrap.ps1 on Windows.' >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  elif [[ "$mode" != "--install" ]]; then
    printf '%s\n' 'Homebrew is missing. Review packages/Brewfile or use --install for a full bootstrap.' >&2
    exit 1
  else
    installer="$(mktemp)"
    trap 'rm -f "$installer"' EXIT
    curl --proto '=https' --tlsv1.2 --fail --show-error --location https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh --output "$installer"
    /bin/bash "$installer"
    if [[ -x /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
      eval "$(/usr/local/bin/brew shellenv)"
    else
      printf '%s\n' 'Homebrew installer did not produce an expected executable.' >&2
      exit 1
    fi
  fi
fi
case "$mode" in
  --diff)
    printf '%s\n' 'Checking packages/Brewfile only. Pi, Herdr core, and settings are not checked.'
    HOMEBREW_NO_AUTO_UPDATE=1 brew bundle check --file packages/Brewfile --no-upgrade --verbose
    ;;
  --sync)
    HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew bundle install --file packages/Brewfile --no-upgrade
    ;;
  --install)
    brew bundle install --file packages/Brewfile --no-upgrade
    uv run --no-project --python 3.14 tools/provision.py --install --skip-packages
    ;;
esac
