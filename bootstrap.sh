#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${1:-}" != "--install" ]]; then
  printf '%s\n' 'Plan: install Homebrew packages, Pi, and its shared packages.' 'No changes made. Use --install to install.'
  exit 0
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  printf '%s\n' 'This bootstrap is for macOS. Use bootstrap.ps1 on Windows.' >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
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
brew bundle --file packages/Brewfile --no-upgrade
uv run --no-project --python 3.14 tools/provision.py --install --skip-packages
