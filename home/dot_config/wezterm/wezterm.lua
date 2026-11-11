local wezterm = require("wezterm")
local config = wezterm.config_builder()

local is_windows = wezterm.target_triple:find("windows", 1, true) ~= nil
local mod = is_windows and "CTRL|SHIFT" or "SUPER|SHIFT"

local function short_path(path)
  local home = wezterm.home_dir:gsub("\\", "/")
  path = path:gsub("\\", "/")
  if path == home then
    return "~"
  end

  if path:sub(1, #home + 1) == home .. "/" then
    return "~" .. path:sub(#home + 1)
  end

  return path
end

local function split_workspace_when_ready(window, name, path, attempt)
  local active_pane = window:active_pane()
  if window:active_workspace() == name and active_pane then
    local active_tab = window:active_tab()
    local panes = active_tab and active_tab:panes() or {}
    if #panes == 1 then
      window:perform_action(
        wezterm.action.SplitHorizontal({
          domain = "CurrentPaneDomain",
          cwd = path,
        }),
        active_pane
      )
    end
    return
  end

  if attempt >= 50 then
    wezterm.log_error("Timed out waiting to split workspace " .. name)
    return
  end

  wezterm.time.call_after(0.1, function()
    split_workspace_when_ready(window, name, path, attempt + 1)
  end)
end

local function open_workspace(window, pane, path)
  path = path:gsub("\\", "/"):gsub("%s+$", ""):gsub("/+$", "")
  local name = path:match("([^/]+)$")
  if not name or name == "" then
    return
  end

  window:perform_action(
    wezterm.action.SwitchToWorkspace({
      name = name,
      spawn = { cwd = path },
    }),
    pane
  )

  -- Split after the workspace switch; preserve existing layouts.
  split_workspace_when_ready(window, name, path, 0)
end

local open_folder_workspace = wezterm.action_callback(function(window, pane)
  local command
  if is_windows then
    command = {
      "pwsh.exe", "-NoLogo", "-NoProfile", "-STA", "-Command",
      [=[Add-Type -AssemblyName System.Windows.Forms
$dialog = [System.Windows.Forms.FolderBrowserDialog]::new()
$dialog.Description = 'Open folder as WezTerm workspace'
try {
  if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Write($dialog.SelectedPath)
  }
} finally { $dialog.Dispose() }]=],
    }
  else
    command = {
      "/usr/bin/osascript", "-e",
      'POSIX path of (choose folder with prompt "Open folder as WezTerm workspace")',
    }
  end
  local success, path, stderr = wezterm.run_child_process(command)
  if success and path and path:match("%S") then
    open_workspace(window, pane, path)
  elseif not success and not (stderr or ""):find("%-128") then
    wezterm.log_error("Folder selection failed: " .. (stderr or "no error detail"))
  end
end)

wezterm.on("update-status", function(window)
  local pane = window:active_pane()
  local cwd = pane and pane.current_working_dir
  local cwd_path = cwd and cwd.path or ""
  local workspace = window:active_workspace() or "default"
  -- Keep status text clear of macOS window controls.
  window:set_right_status(workspace .. " • " .. short_path(cwd_path))
end)

-- `wezwk PATH` sends this event from a shell running in WezTerm.
wezterm.on("user-var-changed", function(window, pane, name, value)
  if name == "open_workspace" and value and value ~= "" then
    open_workspace(window, pane, value)
  end
end)

wezterm.on("augment-command-palette", function()
  return {
    {
      brief = "Open Folder as Workspace",
      action = open_folder_workspace,
    },
  }
end)

config.font = wezterm.font_with_fallback(is_windows and {
  "JetBrainsMono Nerd Font", "JetBrains Mono", "Consolas",
} or {
  "JetBrainsMono Nerd Font", "JetBrains Mono", "SF Mono", "Menlo",
})
config.font_size = 13.0

config.color_scheme = "Solarized Dark Higher Contrast (Gogh)"
config.use_fancy_tab_bar = true
config.tab_max_width = 32
config.audible_bell = "Disabled"
config.visual_bell = {
  fade_in_function = "EaseIn",
  fade_in_duration_ms = 80,
  fade_out_function = "EaseOut",
  fade_out_duration_ms = 220,
  target = "BackgroundColor",
}
config.colors = {
  visual_bell = "#3a2f00",
}
config.window_padding = {
  left = "0.75cell",
  right = "0.5cell",
  top = "0.0cell",
  bottom = "0.0cell",
}

config.window_decorations = is_windows and "TITLE|RESIZE" or "INTEGRATED_BUTTONS|RESIZE"

config.default_prog = is_windows and { "pwsh.exe", "-NoLogo" } or { "/bin/zsh", "-l" }

local keys = {
  {
    key = "w",
    mods = mod,
    action = wezterm.action.PromptInputLine({
      description = "Switch to workspace",
      action = wezterm.action_callback(function(window, pane, line)
        if line and line ~= "" then
          window:perform_action(wezterm.action.SwitchToWorkspace({ name = line }), pane)
        end
      end),
    }),
  },
  {
    key = "r",
    mods = mod,
    action = wezterm.action.PromptInputLine({
      description = "Rename workspace",
      action = wezterm.action_callback(function(window, _, line)
        if line and line ~= "" then
          local old = window:active_workspace() or "default"
          wezterm.mux.rename_workspace(old, line)
        end
      end),
    }),
  },
  {
    key = "l",
    mods = mod,
    action = wezterm.action.ShowLauncherArgs({
      flags = "FUZZY|WORKSPACES|LAUNCH_MENU_ITEMS",
    }),
  },
}

table.insert(keys, {
  key = "o",
  mods = mod,
  action = open_folder_workspace,
})

config.keys = keys

return config
