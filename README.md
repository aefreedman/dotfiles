# Dotfiles

Windows and macOS dotfiles managed with chezmoi.

## Install tools

Run from this directory. The bootstrap scripts preview by default; installation requires a flag.

macOS:

```sh
bash bootstrap.sh
bash bootstrap.sh --install
```

Windows PowerShell:

```powershell
./bootstrap.ps1
./bootstrap.ps1 -Install
```

macOS uses Homebrew; Windows requires WinGet from Microsoft App Installer. Resolve package/source agreements in WinGet if installation stops on one. Herdr core is installed and checked separately from the app.

On macOS, install [Xcode from the App Store](https://apps.apple.com/app/xcode/id497799835).

Pi uses its [official installer](https://pi.dev/docs/latest/quickstart). Migrate package-manager installations to the official installer first, keeping `~/.pi/agent` intact. The shared Pi packages are listed in `packages/manifest.json`.

macOS uses Node 24 LTS; Windows follows `OpenJS.NodeJS.LTS`. Review both when changing Node versions. Windows uses WezTerm nightly because Pi documents [terminal bugs in the old stable build](https://pi.dev/docs/latest/windows).

## Apply configuration

Back up existing shell and terminal configs outside this repo, then review the diff:

```sh
chezmoi --source . diff
chezmoi --source . --interactive apply
```

chezmoi manages files under `home/`. It does not run installers or replace your global Git config, active PowerShell profile, or app settings.

Preview the app-setting merges and profile integration:

```sh
uv run --no-project --python 3.14 tools/preferences.py
uv run --no-project --python 3.14 tools/integrate.py
```

Apply them after review:

```sh
uv run --no-project --python 3.14 tools/preferences.py --apply
uv run --no-project --python 3.14 tools/integrate.py --apply
```

These helpers preserve unrelated settings and existing optional Pi packages. They back up changed files under `~/.local/state/dotfiles/backups/`; those backups do not cover chezmoi targets. Writes are atomic per file, not across a whole phase. Inspect failures and backups before retrying.

Existing Oh My Posh initialization in a PowerShell profile needs review before integration. Herdr's theme picker can override the shared Solarized defaults. Reopen terminals after PATH or font changes; do not restart a Herdr core with active work.

## Local preferences

- Set `DOTFILES_THEME=solarized-light` for the light prompt; dark is the default.
- `wezwk [directory]` opens a workspace in the current WezTerm window.
- Private shell overrides belong in `~/.config/dotfiles/local.zprofile`, `local.zshrc`, or `local.ps1`.
- Credentials and authentication state stay outside this repo.

## Tests

```sh
uv run --no-project --python 3.14 -m unittest discover -s tests -v
```
