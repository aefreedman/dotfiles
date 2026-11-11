local home = os.getenv("HOME") or os.getenv("USERPROFILE")
if not home or home == "" then
  error("Home directory is not set")
end
return dofile(home .. "/.config/wezterm/wezterm.lua")
