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

## Pi model baseline

Preview or apply only `config/pi-models.json`:

```sh
uv run --no-project --python 3.14 tools/preferences.py --pi-models
uv run --no-project --python 3.14 tools/preferences.py --pi-models --apply
```

Apply checks that the exact provider/model IDs are available in Pi before writing. Sign in to OpenAI separately on each machine if needed. This only manages the startup provider, model, thinking level, and model cycle; per-model thinking overrides, subagent settings, saved profiles, and auth stay local. Run `/reload` after applying and check the defaults in a new session.

## Herdr terminal width

With Herdr App running, apply just the width layout and mod from the repo root:

```sh
chezmoi --source . --less-interactive apply \
  ~/.config/herdr-app/mods/terminal-width-status \
  ~/.config/herdr-app/layouts/half-width.json
herdr-app do layout.switch '{"name":"half-width"}'
```

**Max width** in the status bar sets the terminal cap and alignment. Click **Full width** to remove the cap, and click it again to restore your previous width and alignment. These preferences stay local, starting at 750 px and left-aligned on a fresh install. Herdr can rewrite the live layout: review and back up any manual layout edits before applying updates. The repo does not manage Herdr session or Core machine state.

## Herdr Markdown pane

Apply the viewer independently of your layout:

```sh
chezmoi --source . --less-interactive apply ~/.config/herdr-app/mods/markdown-viewer
herdr-app do pane.split '{"direction":"right","mod":"markdown-viewer","props":{"file":"/absolute/path/to/note.md"}}'
```

The pane is read-only and refreshes when an agent or editor saves the file. Use an absolute path on the machine running the Herdr App, not the terminal's remote machine. The mod needs no credentials or helper process.

## Local preferences

- Set `DOTFILES_THEME=solarized-light` for the light prompt and command-line highlighting in zsh and PowerShell; dark is the default. Select the matching Solarized background in your terminal separately.
- Both shells use `home/dot_config/dotfiles/solarized.conf`. In zsh, interactive `#` comments are enabled when highlighting loads.
- `wezwk [directory]` opens a workspace in the current WezTerm window.
- Private shell overrides belong in `~/.config/dotfiles/local.zprofile`, `local.zshrc`, or `local.ps1`.
- Credentials and authentication state stay outside this repo.

## Tests

```sh
uv run --no-project --python 3.14 -m unittest discover -s tests -v
```
