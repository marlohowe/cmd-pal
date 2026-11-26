# CMD Pal

CMD Pal is a small Tkinter launcher for Windows. It can search installed apps
and files, keep favorites and recent apps, run saved website/program shortcuts,
and provide a quick calculator and explicit web search.

## Run

Install Python 3.10 or newer, then run:

```powershell
python .\CMD_Pal.py
```

No third-party packages are required. On Windows, the default global launcher
shortcut is `Shift+?`; it can be changed from **Settings**.

## Features

- **Apps:** search detected Start Menu shortcuts and installed programs.
- **Favorites:** press `Ctrl+D` to favorite or unfavorite the selected app or
  shortcut. Favorites and recently launched apps are saved locally.
- **Files:** search a selected folder by filename.
- **Commands:** save website URLs and direct program paths. Programs are
  launched without a shell; only add files you trust.
- **Tools:** calculate basic arithmetic safely or open a Google search when you
  explicitly choose **Search Web**.
- **Settings:** switch themes, change the hotkey, or launch a selected `.exe`
  installer.

Settings are stored in `%APPDATA%\CMDPal\settings.json` (or
`~\CMDPal\settings.json` when `%APPDATA%` is unavailable). Website shortcuts and
web searches open a browser only after you explicitly launch them.

## Test

```powershell
python -m unittest discover -s tests
```
