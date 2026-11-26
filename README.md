# CMD Pal

CMD Pal is a small Tkinter launcher for Windows. It can search installed apps
and files, keep favorites and recent apps, run saved website/program shortcuts,
and provide a quick calculator and explicit web search.

## Run

Install Python 3.10 or newer, then run the source version:

```powershell
python .\CMD_Pal.py
```

For a source run without a terminal window, use `pythonw`:

```powershell
pythonw .\CMD_Pal.py
```

On Windows, the default global launcher shortcut is `Shift+?`; it can be
changed from **Settings**. It opens a compact launcher with a search field and
icons for each tab, with matching results shown underneath. Use the Up/Down
arrow keys and Enter to open the highlighted result, or choose a tab icon to
bring the full app forward on that screen. The full workspace remains on its
current screen when hidden or reopened.

The results view uses Windows' actual app and file-association icons when
available, with compact type icons as a fallback. In **Settings → Personalize**,
choose dark/light appearance, a preset or
custom accent color, comfortable/compact result spacing, and whether icons are
shown. These preferences are saved locally.

The interface uses a persistent left navigation rail, a larger search/results
workspace, and visible vertical scrollbars with position thumbs in both results
and Settings. The mouse wheel scrolls the Settings page.

## Windows executable

Run `.\build.ps1` in PowerShell on Windows to build the standalone,
no-console executable at `dist\CMD-Pal.exe`. The script installs the pinned
PyInstaller build dependency from `requirements-build.txt`.

### Authenticode signing and SmartScreen

The build is unsigned by default. To sign it, obtain a code-signing certificate
from a trusted certificate authority, install it with its private key in the
current Windows user's `Personal` certificate store (`CurrentUser\My`), and
set `CMDPAL_SIGNING_CERT_THUMBPRINT` to its 40-character thumbprint before
running `.\build.ps1`. The script signs with SHA-256, adds an RFC 3161 timestamp,
and verifies the signature. For example:

```powershell
$env:CMDPAL_SIGNING_CERT_THUMBPRINT = "YOUR_CERTIFICATE_THUMBPRINT"
.\build.ps1
```

Keep the certificate's private key secure; never commit or upload it to the
repository. A self-signed certificate does not establish a trusted publisher.
Signing identifies the publisher, but does not guarantee that SmartScreen will
stop warning: Microsoft reputation checks can still warn on new or uncommon
downloads, and reputation is affected by the certificate and download history.
Use a certificate issued to the actual publisher and distribute the exact
signed executable; rebuilding or modifying it invalidates its signature.

The `.py` source remains available as `CMD_Pal.py`. The packaged app and source
are published together in the repository's GitHub Releases.

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
  installer. Enable **Start CMD Pal when I sign in** to add it to the current
  Windows user's startup registry; the startup copy opens minimized. Use
  **Check for Updates** to look for a GitHub release, then download and open a
  checksum-verified update when one is available.

Settings are stored in `%APPDATA%\CMDPal\settings.json` (or
`~\CMDPal\settings.json` when `%APPDATA%` is unavailable). Website shortcuts and
web searches open a browser only after you explicitly launch them.

## Test

```powershell
python -m unittest discover -s tests
```
