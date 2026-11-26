import ast
import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path
from tkinter import colorchooser, filedialog, ttk
from urllib.parse import quote_plus, urlparse

try:
    import winreg
except ImportError:
    winreg = None


BG = "#0c0e16"
PANEL = "#191f2c"
SIDEBAR = "#111723"
BORDER = "#2a3343"
ACCENT = "#75f0ad"
TEXT = "#f4f6ff"
MUTED = "#929db0"
SELECTED = "#234b3b"
HIBERNATE_COMMAND = "__CMD_HIBERNATE__"
STARTUP_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REGISTRY_NAME = "CMDPal"
APP_VERSION = "1.4.0"
LATEST_RELEASE_API = "https://api.github.com/repos/marlohowe/cmd-pal/releases/latest"
MAX_UPDATE_BYTES = 150 * 1024 * 1024
ACCENT_PRESETS = {
    "Mint": "#75f0ad",
    "Blue": "#76a9ff",
    "Violet": "#c18cff",
    "Amber": "#ffc46b",
    "Rose": "#ff83a8",
}
FILE_ICON_TYPES = {
    ".pdf": "pdf",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".webp": "image", ".svg": "image", ".ico": "image",
    ".mp4": "video", ".mkv": "video", ".mov": "video", ".avi": "video",
    ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".m4a": "audio",
    ".zip": "archive", ".7z": "archive", ".rar": "archive", ".tar": "archive",
    ".py": "code", ".js": "code", ".ts": "code", ".html": "code",
    ".css": "code", ".json": "code", ".go": "code", ".rs": "code",
    ".exe": "executable", ".msi": "executable", ".bat": "code", ".ps1": "code",
    ".doc": "document", ".docx": "document", ".txt": "document", ".rtf": "document",
    ".xls": "spreadsheet", ".xlsx": "spreadsheet", ".csv": "spreadsheet",
    ".ppt": "presentation", ".pptx": "presentation",
}


def result_icon_type(name, target, kind, custom_commands=()):
    if kind == "file":
        return FILE_ICON_TYPES.get(Path(name).suffix.lower(), "document")
    if kind == "hibernate":
        return "power"
    if kind == "result":
        return "calculator"
    if kind == "command":
        for command in custom_commands:
            if target == "cmdpal:" + command["type"] + ":" + command["name"]:
                return "website" if command["type"] == "website" else "app"
        return "website"
    lowered = name.lower()
    if any(term in lowered for term in ("chrome", "firefox", "browser", "edge", "opera")):
        return "browser"
    if any(term in lowered for term in ("music", "spotify", "audio")):
        return "audio"
    if any(term in lowered for term in ("video", "movie", "vlc")):
        return "video"
    if any(term in lowered for term in ("photo", "paint", "image")):
        return "image"
    return "app"


def blend_colors(background, foreground, ratio):
    bg = tuple(int(background[index:index + 2], 16) for index in (1, 3, 5))
    fg = tuple(int(foreground[index:index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(
        f"{round(bg[index] * (1 - ratio) + fg[index] * ratio):02x}"
        for index in range(3)
    )


def calculate(expression):
    """Evaluate a small arithmetic grammar without executing Python code."""
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 128:
        raise ValueError("Enter a short arithmetic expression.")

    tree = ast.parse(expression, mode="eval")
    count = 0

    def visit(node, depth=0):
        nonlocal count
        count += 1
        if count > 40 or depth > 10:
            raise ValueError("Expression is too complex.")
        if isinstance(node, ast.Expression):
            return visit(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = visit(node.operand, depth + 1)
            value = operand if isinstance(node.op, ast.UAdd) else -operand
        elif isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        ):
            left = visit(node.left, depth + 1)
            right = visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.Div):
                value = left / right
            elif isinstance(node.op, ast.FloorDiv):
                value = left // right
            elif isinstance(node.op, ast.Mod):
                value = left % right
            else:
                if abs(right) > 12 or abs(left) > 1e12:
                    raise ValueError("Exponent or base is too large.")
                value = left ** right
        else:
            raise ValueError("Only numbers and basic arithmetic operators are allowed.")

        if isinstance(value, complex) or not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("Result is outside the supported range.")
        return value

    try:
        return visit(tree)
    except (ZeroDivisionError, OverflowError) as error:
        raise ValueError("That calculation is undefined or too large.") from error


def build_startup_command(executable, script_path, frozen, pythonw_path=None):
    if frozen:
        return subprocess.list2cmdline([str(executable), "--startup"])
    if not pythonw_path or not Path(pythonw_path).is_file():
        raise OSError("pythonw.exe was not found; install the packaged app for quiet startup.")
    return subprocess.list2cmdline([
        str(pythonw_path), str(Path(script_path).resolve()), "--startup"
    ])


def is_hex_color(value):
    return (
        isinstance(value, str) and len(value) == 7 and value.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in value[1:])
    )


def parse_release_version(tag):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag or "")
    if not match:
        raise ValueError("The release tag is not a supported version.")
    return tuple(int(part) for part in match.groups())


def parse_release_update(release):
    if not isinstance(release, dict):
        raise ValueError("GitHub returned an invalid release response.")
    tag = release.get("tag_name")
    latest_version = parse_release_version(tag)
    if latest_version <= parse_release_version(APP_VERSION):
        return None

    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("The latest release has an invalid asset list.")
    asset = next(
        (item for item in assets
         if isinstance(item, dict) and item.get("name") == "CMD-Pal.exe"),
        None,
    )
    if not isinstance(asset, dict):
        raise ValueError("The latest release does not include CMD-Pal.exe.")
    download_url = asset.get("browser_download_url", "")
    digest = asset.get("digest", "")
    parsed_url = urlparse(download_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "github.com":
        raise ValueError("The release download URL is not a trusted GitHub HTTPS link.")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("GitHub did not provide a valid SHA-256 checksum for this update.")
    return {
        "tag": tag,
        "version": latest_version,
        "url": download_url,
        "digest": digest.split(":", 1)[1].lower(),
    }


def download_verified_update(update, updates_directory, urlopen=None):
    tag = update.get("tag", "")
    parse_release_version(tag)
    download_url = update.get("url", "")
    parsed_url = urlparse(download_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "github.com":
        raise ValueError("The release download URL is not a trusted GitHub HTTPS link.")
    expected_digest = update.get("digest", "")
    if not isinstance(expected_digest, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", expected_digest
    ):
        raise ValueError("The release checksum is invalid.")
    if urlopen is None:
        urlopen = urllib.request.urlopen

    update_directory = Path(updates_directory) / tag
    update_directory.mkdir(parents=True, exist_ok=True)
    destination = update_directory / "CMD-Pal.exe"
    temporary_path = update_directory / "CMD-Pal.exe.download"
    digest = hashlib.sha256()
    total_bytes = 0
    try:
        request = urllib.request.Request(
            download_url, headers={"User-Agent": "CMD-Pal-Updater"}
        )
        with urlopen(request, timeout=60) as response:
            with temporary_path.open("wb") as downloaded:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPDATE_BYTES:
                        raise ValueError("The update download exceeded the size limit.")
                    digest.update(chunk)
                    downloaded.write(chunk)
        if digest.hexdigest() != expected_digest.lower():
            raise ValueError("The update checksum did not match GitHub's release metadata.")
        with temporary_path.open("rb") as downloaded:
            if downloaded.read(2) != b"MZ":
                raise ValueError("The downloaded update is not a Windows executable.")
        os.replace(temporary_path, destination)
        return destination
    except (OSError, ValueError):
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass
        raise


class CMDPal:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"CMD Pal {APP_VERSION}")
        self.root.geometry("1060x720")
        self.root.minsize(860, 600)
        self.root.configure(bg=BG)

        self.mode = "apps"
        self.folder = Path.home()
        self.apps = []
        self.results = []
        self.selected = 0
        self.generation = 0
        self.hotkey_thread_id = None
        self.closing = False
        self.quick_window = None
        self.updated_launch = "--migrate-startup" in sys.argv[1:]
        self.hotkey_retry_scheduled = False
        self.config_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "CMDPal" / "settings.json"
        self.settings = {
            "theme": "dark",
            "accent": "Mint",
            "custom_accent": ACCENT_PRESETS["Mint"],
            "density": "Comfortable",
            "show_icons": True,
            "hotkey": "Shift+?",
            "favorites": [],
            "recent": [],
            "custom_commands": [],
            "run_on_startup": False,
        }
        self.load_settings()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Up>", self.move_up)
        self.root.bind("<Down>", self.move_down)
        self.root.bind("<Return>", self.launch_selected)
        self.root.bind("<Escape>", self.clear)
        self.root.bind("<Control-d>", self.toggle_favorite)

        threading.Thread(target=self.scan_apps, daemon=True).start()
        if os.name == "nt":
            threading.Thread(target=self.global_hotkey, daemon=True).start()
        if "--startup" in sys.argv[1:]:
            self.root.after(0, self.root.iconify)
        if "--migrate-startup" in sys.argv[1:] and os.name == "nt":
            self.root.after(250, self.migrate_startup)

    def palette(self):
        accent_name = self.settings.get("accent", "Mint")
        accent = (self.settings.get("custom_accent", ACCENT_PRESETS["Mint"])
                  if accent_name == "Custom"
                  else ACCENT_PRESETS.get(accent_name, ACCENT_PRESETS["Mint"]))
        if self.settings["theme"] == "light":
            return {
                "bg": "#f3f5fa", "panel": "#ffffff", "accent": accent,
                "text": "#182235", "muted": "#647084",
                "selected": blend_colors("#ffffff", accent, 0.15),
                "sidebar": "#e9edf4", "border": "#d4dbe6",
                "scroll_trough": "#e2e7ef", "scroll_thumb": "#9ba6b7",
                "scroll_active": "#748197",
            }
        return {"bg": BG, "panel": PANEL, "accent": accent,
                "text": TEXT, "muted": MUTED, "selected": blend_colors(PANEL, accent, 0.24),
                "sidebar": SIDEBAR, "border": BORDER,
                "scroll_trough": "#111722", "scroll_thumb": "#697587",
                "scroll_active": "#98a3b4"}

    def gradient(self, width, height):
        image = tk.PhotoImage(width=width, height=height)
        colors = ((35, 105, 180), (105, 65, 190), (25, 175, 135))
        for x in range(width):
            ratio = x / max(1, width - 1)
            if ratio < 0.5:
                t, a, b = ratio * 2, colors[0], colors[1]
            else:
                t, a, b = (ratio - 0.5) * 2, colors[1], colors[2]
            rgb = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            image.put("#%02x%02x%02x" % rgb, to=(x, 0, x + 1, height))
        return image

    def build_ui(self):
        self.ttk_style = ttk.Style(self.root)
        try:
            self.ttk_style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure_ttk_theme()
        c = self.palette()
        self.shell = tk.Frame(self.root, bg=c["bg"])
        self.shell.pack(fill="both", expand=True)
        self.shell.grid_rowconfigure(0, weight=1)
        self.shell.grid_columnconfigure(1, weight=1)

        self.sidebar = tk.Frame(self.shell, bg=c["sidebar"], width=220)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        logo = tk.Frame(self.sidebar, bg=c["sidebar"])
        logo.pack(fill="x", padx=20, pady=(25, 30))
        tk.Label(logo, text="CP", bg=c["accent"], fg=c["bg"],
                 font=("Segoe UI", 14, "bold"), width=3, height=1
                 ).pack(side="left", padx=(0, 10), ipady=5)
        brand = tk.Frame(logo, bg=c["sidebar"])
        brand.pack(side="left", anchor="center")
        tk.Label(brand, text="CMD PAL", bg=c["sidebar"], fg=c["text"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(brand, text="DESKTOP LAUNCHER", bg=c["sidebar"], fg=c["muted"],
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(1, 0))
        tk.Label(self.sidebar, text="WORKSPACE", bg=c["sidebar"], fg=c["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(0, 7))
        self.tab_buttons = {}
        for mode, title in (
            ("apps", "▣   Apps"), ("favorites", "★   Favorites"),
            ("files", "▤   Files"), ("commands", "⌘   Shortcuts"),
            ("tools", "∑   Tools"), ("settings", "⚙   Settings"),
        ):
            button = tk.Button(
                self.sidebar, text=title,
                command=lambda selected=mode: self.change_mode(selected),
                font=("Segoe UI", 10, "bold"), relief="flat", padx=15, pady=11,
                cursor="hand2", anchor="w", width=20, bd=0,
            )
            button.pack(fill="x", padx=10, pady=2)
            self.tab_buttons[mode] = button
        sidebar_footer = tk.Frame(self.sidebar, bg=c["sidebar"])
        sidebar_footer.pack(side="bottom", fill="x", padx=20, pady=22)
        tk.Frame(sidebar_footer, bg=c["border"], height=1).pack(fill="x", pady=(0, 14))
        tk.Label(sidebar_footer, text="QUICK OPEN", bg=c["sidebar"], fg=c["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.header_hotkey_label = tk.Label(
            sidebar_footer, text=self.settings["hotkey"].upper(),
            bg=c["sidebar"], fg=c["accent"], font=("Segoe UI", 11, "bold")
        )
        self.header_hotkey_label.pack(anchor="w", pady=(4, 2))
        tk.Label(sidebar_footer, text="Press anywhere to open quick launcher",
                 bg=c["sidebar"], fg=c["muted"], font=("Segoe UI", 8),
                 wraplength=175, justify="left").pack(anchor="w")

        self.main = tk.Frame(self.shell, bg=c["bg"])
        self.main.grid(row=0, column=1, sticky="nsew", padx=30, pady=24)
        self.main.grid_rowconfigure(4, weight=1)
        self.main.grid_columnconfigure(0, weight=1)
        heading = tk.Frame(self.main, bg=c["bg"])
        heading.pack(fill="x", pady=(0, 20))
        heading_text = tk.Frame(heading, bg=c["bg"])
        heading_text.pack(side="left")
        self.page_title_label = tk.Label(
            heading_text, text="Apps", bg=c["bg"], fg=c["text"],
            font=("Segoe UI", 23, "bold")
        )
        self.page_title_label.pack(anchor="w")
        self.page_subtitle_label = tk.Label(
            heading_text, text="Find and launch something quickly.",
            bg=c["bg"], fg=c["muted"], font=("Segoe UI", 10)
        )
        self.page_subtitle_label.pack(anchor="w", pady=(2, 0))
        tk.Label(heading, text="READY WHEN YOU ARE", bg=c["bg"], fg=c["accent"],
                 font=("Segoe UI", 8, "bold")).pack(side="right", anchor="s", pady=5)

        self.search_frame = tk.Frame(
            self.main, bg=c["panel"], highlightthickness=1,
            highlightbackground=c["border"],
        )
        tk.Label(self.search_frame, text="⌕", bg=c["panel"], fg=c["accent"],
                 font=("Segoe UI", 20)).pack(side="left", padx=(15, 8))
        self.search = tk.Entry(
            self.search_frame, bg=c["panel"], fg=c["text"],
            insertbackground=c["accent"], font=("Segoe UI", 13),
            relief="flat", borderwidth=0,
        )
        self.search.pack(side="left", fill="x", expand=True, padx=8, pady=14)
        self.search.bind("<KeyRelease>", self.on_search)

        self.folder_frame = tk.Frame(self.main, bg=c["bg"])
        self.folder_label = tk.Label(self.folder_frame, text="Folder: " + str(self.folder),
                                     bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9), anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True, padx=2)
        tk.Button(self.folder_frame, text="Choose Folder", command=self.choose_folder,
                  bg=c["panel"], fg=c["accent"], relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=10, pady=7, cursor="hand2").pack(side="right")

        self.commands_frame = tk.Frame(self.main, bg=c["bg"])
        self.build_commands_controls()
        self.tools_frame = tk.Frame(self.main, bg=c["bg"])
        self.build_tools_controls()
        self.status_row = tk.Frame(self.main, bg=c["bg"])
        self.status = tk.Label(self.status_row, text="Loading applications...", bg=c["bg"],
                               fg=c["muted"], font=("Segoe UI", 9), anchor="w")
        self.status.pack(side="left", fill="x", expand=True, pady=9)
        self.result_count_label = tk.Label(self.status_row, text="", bg=c["bg"],
                                           fg=c["muted"], font=("Segoe UI", 8))
        self.result_count_label.pack(side="right", pady=9)

        self.result_outer = tk.Frame(self.main, bg=c["border"], padx=1, pady=1)
        inner = tk.Frame(self.result_outer, bg=c["panel"])
        inner.pack(fill="both", expand=True)
        self.listbox = ttk.Treeview(
            inner, columns=("type",), show="tree headings",
            style="CMD.Treeview", selectmode="browse",
        )
        self.listbox.heading("#0", text="Name", anchor="w")
        self.listbox.heading("type", text="TYPE", anchor="w")
        self.listbox.column("#0", anchor="w", width=450, minwidth=200, stretch=True)
        self.listbox.column("type", anchor="w", width=130, minwidth=100, stretch=False)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        self.list_scrollbar = ttk.Scrollbar(
            inner, orient="vertical", command=self.listbox.yview,
            style="CMD.Vertical.TScrollbar",
        )
        self.listbox.configure(yscrollcommand=self.list_scrollbar.set)
        self.list_scrollbar.pack(side="right", fill="y", padx=(4, 8), pady=10)
        self.listbox.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.listbox.bind("<Double-Button-1>", self.launch_selected)
        self.icon_cache = {}
        self.result_images = []

        self.footer = tk.Frame(self.main, bg=c["bg"])
        self.favorite_button = tk.Button(
            self.footer, text="☆ Favorite  (Ctrl+D)", command=self.toggle_favorite,
            bg=c["panel"], fg=c["accent"], relief="flat", font=("Segoe UI", 8, "bold"),
            padx=10, pady=7, cursor="hand2",
        )
        self.remove_command_button = tk.Button(
            self.footer, text="Remove command", command=self.remove_custom_command,
            bg=c["panel"], fg=c["accent"], relief="flat", font=("Segoe UI", 8, "bold"),
            padx=10, pady=7, cursor="hand2",
        )
        self.remove_command_button.pack_forget()
        self.footer_hint = tk.Label(
            self.footer, text="↑ ↓ Move     ENTER Open     ESC Clear",
            bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8),
        )
        self.hotkey_label = self.header_hotkey_label

        self.settings_frame = tk.Frame(self.main, bg=c["bg"])
        self.build_settings_ui()
        self.apply_theme()
        self.update_tabs()
        self.update_mode_panels()

    def build_commands_controls(self):
        c = self.palette()
        tk.Label(self.commands_frame, text="Add a shortcut (websites open in your browser; programs launch directly)",
                 bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        row = tk.Frame(self.commands_frame, bg=c["bg"])
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Name", bg=c["bg"], fg=c["muted"],
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 3))
        self.command_name = tk.Entry(row, width=17, bg=c["panel"], fg=c["text"])
        self.command_name.pack(side="left", padx=(0, 5), ipady=4)
        self.command_type = tk.StringVar(value="Website")
        ttk.Combobox(row, textvariable=self.command_type, values=("Website", "Program"),
                     width=9, state="readonly").pack(side="left", padx=(0, 5))
        tk.Label(row, text="Target", bg=c["bg"], fg=c["muted"],
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 3))
        self.command_target = tk.Entry(row, bg=c["panel"], fg=c["text"])
        self.command_target.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=4)
        tk.Button(row, text="ADD", command=self.add_custom_command, bg=c["accent"],
                  fg=c["bg"], relief="flat", padx=10).pack(side="right")

    def build_tools_controls(self):
        c = self.palette()
        tk.Label(self.tools_frame, text="Enter an arithmetic expression, or search the web explicitly.",
                 bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        row = tk.Frame(self.tools_frame, bg=c["bg"])
        row.pack(fill="x", pady=4)
        tk.Button(row, text="CALCULATE", command=self.calculate_query, bg=c["accent"],
                  fg=c["bg"], relief="flat", padx=10, pady=5).pack(side="left")
        tk.Button(row, text="SEARCH WEB", command=self.search_web, bg=c["panel"],
                  fg=c["accent"], relief="flat", padx=10, pady=5).pack(side="left", padx=6)

    def build_settings_ui(self):
        c = self.palette()
        self.settings_canvas = tk.Canvas(
            self.settings_frame, bg=c["bg"], highlightthickness=0, borderwidth=0
        )
        scrollbar = ttk.Scrollbar(
            self.settings_frame, orient="vertical", command=self.settings_canvas.yview,
            style="CMD.Vertical.TScrollbar",
        )
        self.settings_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        self.settings_content = tk.Frame(self.settings_canvas, bg=c["bg"])
        self.settings_window = self.settings_canvas.create_window(
            (0, 0), window=self.settings_content, anchor="nw"
        )
        self.settings_content.bind(
            "<Configure>",
            lambda event: self.settings_canvas.configure(
                scrollregion=self.settings_canvas.bbox("all")
            ),
        )
        self.settings_canvas.bind(
            "<Configure>",
            lambda event: self.settings_canvas.itemconfigure(
                self.settings_window, width=event.width
            ),
        )
        tk.Label(self.settings_content, text="Settings", font=("Segoe UI", 20, "bold"),
                 bg=c["bg"], fg=c["accent"]).pack(anchor="w", pady=(4, 2))
        tk.Label(self.settings_content, text="Make CMD Pal work the way you do.",
                 bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        appearance = self.settings_section(self.settings_content, "APPEARANCE")
        appearance.pack(fill="x", pady=4)
        self.theme_var = tk.StringVar(value=self.settings["theme"].title())
        theme_row = tk.Frame(appearance, bg=c["panel"])
        theme_row.pack(anchor="w")
        for label in ("Dark", "Light"):
            tk.Radiobutton(theme_row, text=label, value=label, variable=self.theme_var,
                           bg=c["panel"], fg=c["text"], selectcolor=c["bg"],
                           activebackground=c["panel"]).pack(side="left", padx=(0, 12))

        customize = self.settings_section(self.settings_content, "PERSONALIZE")
        customize.pack(fill="x", pady=4)
        customize_row = tk.Frame(customize, bg=c["panel"])
        customize_row.pack(fill="x")
        self.accent_var = tk.StringVar(value=self.settings["accent"])
        self.pending_custom_accent = self.settings["custom_accent"]
        tk.Label(customize_row, text="Accent color", bg=c["panel"], fg=c["text"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        accent_picker = ttk.Combobox(
            customize_row, textvariable=self.accent_var,
            values=tuple(ACCENT_PRESETS) + ("Custom",), width=12, state="readonly",
        )
        accent_picker.pack(side="left")
        accent_picker.bind("<<ComboboxSelected>>", self.update_accent_preview)
        self.accent_swatch = tk.Label(
            customize_row, text="   ", bg=self.pending_custom_accent, relief="solid", bd=1
        )
        self.accent_swatch.pack(side="left", padx=7)
        tk.Button(
            customize_row, text="Choose color…", command=self.choose_accent_color,
            bg=c["bg"], fg=c["text"], activebackground=c["selected"],
            relief="flat", padx=9, pady=5, cursor="hand2",
        ).pack(side="left", padx=(2, 0))
        density_row = tk.Frame(customize, bg=c["panel"])
        density_row.pack(fill="x", pady=(8, 0))
        tk.Label(density_row, text="Result spacing", bg=c["panel"], fg=c["text"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        self.density_var = tk.StringVar(value=self.settings["density"])
        ttk.Combobox(
            density_row, textvariable=self.density_var,
            values=("Comfortable", "Compact"), width=12, state="readonly",
        ).pack(side="left")
        self.show_icons_var = tk.BooleanVar(value=self.settings["show_icons"])
        tk.Checkbutton(
            customize, text="Show app and file type icons",
            variable=self.show_icons_var, bg=c["panel"], fg=c["text"],
            selectcolor=c["bg"], activebackground=c["panel"],
            activeforeground=c["text"], font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(7, 0))
        tk.Label(
            customize,
            text="Choose a color preset or pick your own. Icons identify app and file types.",
            bg=c["panel"], fg=c["muted"], font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))

        updates = self.settings_section(self.settings_content, "APP UPDATES")
        updates.pack(fill="x", pady=4)
        tk.Label(
            updates, text=f"Installed version: v{APP_VERSION}",
            bg=c["panel"], fg=c["text"], font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            updates,
            text="Check GitHub for a newer release. Updates are downloaded only after you choose to install.",
            bg=c["panel"], fg=c["muted"], font=("Segoe UI", 8),
            wraplength=670, justify="left",
        ).pack(anchor="w", pady=(2, 5))
        update_actions = tk.Frame(updates, bg=c["panel"])
        update_actions.pack(fill="x")
        self.update_check_button = tk.Button(
            update_actions, text="CHECK FOR UPDATES", command=self.check_for_updates,
            bg=c["bg"], fg=c["accent"], activebackground=c["selected"],
            relief="flat", padx=10, pady=6, cursor="hand2",
        )
        self.update_check_button.pack(side="left")
        self.update_install_button = tk.Button(
            update_actions, text="DOWNLOAD & OPEN UPDATE",
            command=self.download_update, bg=c["accent"], fg=c["bg"],
            activebackground=c["selected"], relief="flat", padx=10, pady=6,
            cursor="hand2", state="disabled",
        )
        self.update_install_button.pack(side="left", padx=(7, 0))
        self.update_status = tk.Label(
            updates, text="Updates are checked manually.", bg=c["panel"],
            fg=c["muted"], font=("Segoe UI", 8), wraplength=670, justify="left",
        )
        self.update_status.pack(anchor="w", pady=(5, 0))
        self.available_update = None
        if os.name != "nt":
            self.update_check_button.configure(state="disabled")
            self.update_status.config(text="Windows executable updates are only available on Windows.")

        shortcut = self.settings_section(self.settings_content, "LAUNCH SHORTCUT")
        shortcut.pack(fill="x", pady=4)
        tk.Label(shortcut, text="Global hotkey", bg=c["panel"], fg=c["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.hotkey_var = tk.StringVar(value=self.settings["hotkey"])
        tk.Entry(shortcut, textvariable=self.hotkey_var, width=25,
                 font=("Segoe UI", 10), bg=c["bg"], fg=c["text"],
                 insertbackground=c["accent"], relief="flat"
                 ).pack(anchor="w", pady=5, ipady=4)
        tk.Label(shortcut, text="Default: Shift+?   ·   Example: Ctrl+Alt+K",
                 bg=c["panel"], fg=c["muted"], font=("Segoe UI", 8)).pack(anchor="w")

        startup = self.settings_section(self.settings_content, "WINDOWS STARTUP")
        startup.pack(fill="x", pady=4)
        self.startup_var = tk.BooleanVar(value=self.is_startup_enabled())
        startup_check = tk.Checkbutton(
            startup, text="Start CMD Pal when I sign in",
            variable=self.startup_var, bg=c["panel"], fg=c["text"],
            selectcolor=c["bg"], activebackground=c["panel"],
            activeforeground=c["text"], font=("Segoe UI", 10),
        )
        startup_check.pack(anchor="w")
        if winreg is None:
            startup_check.configure(state="disabled")
        tk.Label(
            startup,
            text="Applies to your Windows account only. The app starts minimized to the taskbar.",
            bg=c["panel"], fg=c["muted"], font=("Segoe UI", 8), wraplength=670,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        installer = self.settings_section(self.settings_content, "INSTALLER")
        installer.pack(fill="x", pady=4)
        tk.Label(installer, text="Choose a Windows .exe installer already on this PC.",
                 bg=c["panel"], fg=c["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        row = tk.Frame(installer, bg=c["panel"])
        row.pack(fill="x", pady=5)
        self.installer_var = tk.StringVar(value="No installer selected")
        tk.Entry(row, textvariable=self.installer_var, state="readonly",
                 bg=c["bg"], fg=c["text"], readonlybackground=c["bg"], relief="flat"
                 ).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(row, text="Browse .EXE", command=self.choose_installer,
                  bg=c["panel"], fg=c["accent"], relief="flat", padx=8, pady=5
                  ).pack(side="left", padx=(6, 0))
        tk.Button(installer, text="RUN INSTALLER", command=self.run_installer,
                  bg=c["accent"], fg=c["bg"], relief="flat", padx=12, pady=7
                  ).pack(anchor="w", pady=3)
        self.installer_status = tk.Label(installer, text="", bg=c["panel"],
                                         fg=c["muted"], font=("Segoe UI", 8))
        self.installer_status.pack(anchor="w", pady=2)
        self.selected_installer = None
        self.settings_message = tk.Label(self.settings_content, text="", bg=c["bg"], fg=c["muted"])
        self.settings_message.pack(anchor="w", pady=(6, 2))
        tk.Button(self.settings_content, text="SAVE SETTINGS", command=self.apply_settings,
                  bg=c["accent"], fg=c["bg"], relief="flat", padx=12, pady=7
                  ).pack(anchor="w", pady=(0, 10))
        self.bind_settings_mousewheel(self.settings_content)

    def choose_accent_color(self):
        chosen = colorchooser.askcolor(
            color=self.pending_custom_accent, title="Choose CMD Pal accent color",
            parent=self.root,
        )[1]
        if chosen:
            self.pending_custom_accent = chosen.lower()
            self.accent_var.set("Custom")
            self.accent_swatch.configure(bg=self.pending_custom_accent)

    def update_accent_preview(self, event=None):
        preset = self.accent_var.get()
        color = self.pending_custom_accent if preset == "Custom" else ACCENT_PRESETS[preset]
        self.accent_swatch.configure(bg=color)

    def settings_section(self, parent, title):
        c = self.palette()
        return tk.LabelFrame(
            parent, text=title, bg=c["panel"], fg=c["accent"],
            font=("Segoe UI", 8, "bold"), padx=10, pady=8,
            bd=1, relief="solid", labelanchor="nw",
        )

    def bind_settings_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self.scroll_settings, add="+")
        for child in widget.winfo_children():
            self.bind_settings_mousewheel(child)

    def scroll_settings(self, event):
        if self.mode == "settings":
            self.settings_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

    def dispatch_update_ui(self, callback, *args):
        if self.closing:
            return
        try:
            self.root.after(0, callback, *args)
        except (RuntimeError, tk.TclError):
            pass

    def check_for_updates(self):
        if os.name != "nt":
            self.update_status.config(text="Windows executable updates are only available on Windows.")
            return
        self.available_update = None
        self.update_check_button.configure(state="disabled")
        self.update_install_button.configure(state="disabled")
        self.update_status.config(text="Checking GitHub for the latest release…")
        threading.Thread(target=self.check_updates_worker, daemon=True).start()

    def check_updates_worker(self):
        try:
            request = urllib.request.Request(
                LATEST_RELEASE_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "CMD-Pal-Updater",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                release = json.loads(response.read().decode("utf-8"))
            update = parse_release_update(release)
            self.dispatch_update_ui(self.finish_update_check, update, None)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            self.dispatch_update_ui(self.finish_update_check, None, str(error))

    def finish_update_check(self, update, error):
        self.update_check_button.configure(state="normal")
        if error:
            self.update_status.config(text=f"Could not check for updates: {error}")
        elif update is None:
            self.update_status.config(text=f"CMD Pal v{APP_VERSION} is up to date.")
        else:
            self.available_update = update
            self.update_status.config(text=f"Version {update['tag']} is available.")
            self.update_install_button.configure(
                text=f"DOWNLOAD & OPEN {update['tag']}", state="normal"
            )

    def download_update(self):
        update = self.available_update
        if not update:
            return
        self.update_check_button.configure(state="disabled")
        self.update_install_button.configure(state="disabled")
        self.update_status.config(text=f"Downloading {update['tag']}…")
        threading.Thread(
            target=self.download_update_worker, args=(update,), daemon=True
        ).start()

    def download_update_worker(self, update):
        try:
            updates_directory = (
                Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                / "CMDPal" / "Updates"
            )
            destination = download_verified_update(update, updates_directory)
            self.dispatch_update_ui(self.launch_downloaded_update, destination, update["tag"])
        except (OSError, ValueError) as error:
            self.dispatch_update_ui(self.finish_update_download, str(error))

    def finish_update_download(self, error):
        self.update_check_button.configure(state="normal")
        self.update_install_button.configure(state="normal")
        self.update_status.config(text=f"Could not download update: {error}")

    def launch_downloaded_update(self, executable, tag):
        try:
            subprocess.Popen(
                [str(executable), "--migrate-startup"],
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            self.finish_update_download(f"Downloaded {tag}, but could not open it: {error}")
            return
        self.close()

    def migrate_startup(self):
        if self.is_startup_enabled():
            try:
                self.set_startup_enabled(True)
            except OSError as error:
                self.status.config(text=f"Could not update startup shortcut: {error}")

    def startup_command(self):
        frozen = getattr(sys, "frozen", False)
        pythonw = None if frozen else Path(sys.executable).with_name("pythonw.exe")
        return build_startup_command(sys.executable, __file__, frozen, pythonw)

    def is_startup_enabled(self):
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY, 0, winreg.KEY_QUERY_VALUE
            ) as key:
                winreg.QueryValueEx(key, STARTUP_REGISTRY_NAME)
            return True
        except OSError:
            return False

    def set_startup_enabled(self, enabled):
        if winreg is None:
            raise OSError("Run on startup is only available on Windows.")
        if enabled:
            command = self.startup_command()
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, STARTUP_REGISTRY_NAME, 0, winreg.REG_SZ, command)
            return
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, STARTUP_REGISTRY_NAME)
        except FileNotFoundError:
            pass

    def load_settings(self):
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return
                if data.get("theme") in ("dark", "light"):
                    self.settings["theme"] = data["theme"]
                if data.get("accent") in tuple(ACCENT_PRESETS) + ("Custom",):
                    self.settings["accent"] = data["accent"]
                if is_hex_color(data.get("custom_accent")):
                    self.settings["custom_accent"] = data["custom_accent"].lower()
                if data.get("density") in ("Comfortable", "Compact"):
                    self.settings["density"] = data["density"]
                if isinstance(data.get("show_icons"), bool):
                    self.settings["show_icons"] = data["show_icons"]
                if isinstance(data.get("hotkey"), str):
                    self.settings["hotkey"] = data["hotkey"]
                if isinstance(data.get("run_on_startup"), bool):
                    self.settings["run_on_startup"] = data["run_on_startup"]
                for key in ("favorites", "recent"):
                    if isinstance(data.get(key), list):
                        self.settings[key] = [item for item in data[key] if isinstance(item, str)]
                if isinstance(data.get("custom_commands"), list):
                    self.settings["custom_commands"] = [
                        item for item in data["custom_commands"]
                        if isinstance(item, dict)
                        and isinstance(item.get("name"), str)
                        and isinstance(item.get("target"), str)
                        and item.get("type") in ("website", "program")
                    ]
        except (OSError, ValueError, TypeError):
            pass

    def save_settings(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

    def choose_installer(self):
        chosen = filedialog.askopenfilename(
            title="Select Windows EXE installer",
            filetypes=[("Windows executable", "*.exe"), ("All files", "*.*")]
        )
        if chosen:
            if Path(chosen).suffix.lower() != ".exe":
                self.installer_status.config(text="Please choose an .exe file.")
                return
            self.selected_installer = Path(chosen)
            self.installer_var.set(str(self.selected_installer))
            self.installer_status.config(text="Installer selected. Click RUN INSTALLER.")

    def run_installer(self):
        installer = self.selected_installer
        if not installer or not installer.is_file():
            self.installer_status.config(text="Choose a valid .exe installer first.")
        elif os.name != "nt":
            self.installer_status.config(text="EXE installers can only be launched on Windows.")
        else:
            try:
                os.startfile(str(installer))
                self.installer_status.config(text=f"Launched {installer.name}. Follow its prompts.")
            except OSError as error:
                self.installer_status.config(text=f"Could not launch installer: {error}")

    def parse_hotkey(self, shortcut):
        parts = [part.strip().lower() for part in shortcut.split("+") if part.strip()]
        aliases = {"control": "ctrl", "windows": "win", "super": "win"}
        parts = [aliases.get(part, part) for part in parts]
        mods = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
        key_names = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
                     "?": 0xBF, "/": 0xBF, "slash": 0xBF}
        keys = [part for part in parts if part not in mods]
        if len(keys) != 1 or not any(part in mods for part in parts):
            raise ValueError("Use a modifier and one key, e.g. Shift+? or Ctrl+Alt+K.")
        key = keys[0]
        if len(key) == 1 and key.isalnum():
            vk = ord(key.upper())
        elif key in key_names:
            vk = key_names[key]
        elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
            vk = 0x70 + int(key[1:]) - 1
        else:
            raise ValueError("Unsupported shortcut key.")
        modifier = 0
        for part in parts:
            if part in mods:
                modifier |= mods[part]
        return modifier, vk

    def apply_settings(self):
        shortcut = self.hotkey_var.get().strip()
        try:
            self.parse_hotkey(shortcut)
        except ValueError as error:
            self.settings_message.config(text=str(error))
            return
        accent = self.accent_var.get()
        if accent not in tuple(ACCENT_PRESETS) + ("Custom",):
            self.settings_message.config(text="Choose a valid accent color.")
            return
        if accent == "Custom" and not is_hex_color(self.pending_custom_accent):
            self.settings_message.config(text="Choose a valid custom accent color.")
            return
        startup_error = None
        try:
            self.set_startup_enabled(self.startup_var.get())
            self.settings["run_on_startup"] = self.startup_var.get()
        except OSError as error:
            self.startup_var.set(self.is_startup_enabled())
            self.settings["run_on_startup"] = self.startup_var.get()
            startup_error = error
        self.settings["theme"] = self.theme_var.get().lower()
        self.settings["hotkey"] = shortcut
        self.settings["accent"] = accent
        self.settings["custom_accent"] = self.pending_custom_accent
        self.settings["density"] = self.density_var.get()
        self.settings["show_icons"] = self.show_icons_var.get()
        saved = self.save_settings()
        self.apply_theme()
        self.update_tabs()
        self.hotkey_label.config(text=shortcut.upper())
        self.update_accent_preview()
        if os.name == "nt":
            self.restart_hotkey()
        if startup_error:
            message = f"Startup setting was not changed: {startup_error}"
        elif not saved:
            message = "Settings applied, but could not be saved."
        else:
            message = "Settings saved."
        self.settings_message.config(text=message)

    def apply_theme(self):
        c = self.palette()
        self.configure_ttk_theme()
        previous = getattr(self, "displayed_palette", c)
        mapping = {previous[key]: c[key] for key in c if key in previous}

        def recolor(widget):
            for option in ("bg", "fg", "activebackground", "activeforeground",
                           "selectbackground", "selectforeground", "insertbackground",
                           "highlightbackground", "selectcolor", "readonlybackground"):
                try:
                    old = widget.cget(option)
                    if old in mapping:
                        widget.configure(**{option: mapping[old]})
                except tk.TclError:
                    pass
            for child in widget.winfo_children():
                recolor(child)

        recolor(self.root)
        self.displayed_palette = c
        if hasattr(self, "icon_cache"):
            self.icon_cache.clear()
            self.set_results(self.results)

    def configure_ttk_theme(self):
        c = self.palette()
        row_height = 38 if self.settings.get("density") == "Comfortable" else 30
        self.ttk_style.configure(
            "CMD.Treeview",
            background=c["panel"], fieldbackground=c["panel"], foreground=c["text"],
            rowheight=row_height, borderwidth=0, font=("Segoe UI", 10),
        )
        self.ttk_style.configure(
            "CMD.Treeview.Heading",
            background=c["sidebar"], foreground=c["muted"],
            font=("Segoe UI", 8, "bold"), relief="flat", padding=(8, 8),
        )
        self.ttk_style.map(
            "CMD.Treeview",
            background=[("selected", c["selected"])],
            foreground=[("selected", c["accent"])],
        )
        self.ttk_style.configure(
            "TCombobox", fieldbackground=c["panel"], background=c["panel"],
            foreground=c["text"], arrowcolor=c["accent"],
        )
        self.ttk_style.map(
            "TCombobox", fieldbackground=[("readonly", c["panel"])],
            selectbackground=[("readonly", c["selected"])],
            selectforeground=[("readonly", c["text"])],
        )
        self.ttk_style.configure(
            "CMD.Vertical.TScrollbar",
            background=c["scroll_thumb"], troughcolor=c["scroll_trough"],
            bordercolor=c["scroll_trough"], arrowcolor=c["muted"],
            darkcolor=c["scroll_thumb"], lightcolor=c["scroll_thumb"],
            gripcount=0, width=13,
        )
        self.ttk_style.map(
            "CMD.Vertical.TScrollbar",
            background=[("pressed", c["scroll_active"]), ("active", c["scroll_active"])],
        )

    def restart_hotkey(self):
        if self.hotkey_thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, 0x0012, 0, 0)
            except OSError:
                pass
        self.root.after(250, lambda: threading.Thread(target=self.global_hotkey, daemon=True).start())

    def global_hotkey(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.hotkey_thread_id = kernel32.GetCurrentThreadId()
        try:
            modifiers, virtual_key = self.parse_hotkey(self.settings["hotkey"])
        except ValueError:
            modifiers, virtual_key = 0x0004, 0xBF
        if not user32.RegisterHotKey(None, 1, modifiers, virtual_key):
            self.root.after(0, lambda: self.status.config(text=f"{self.settings['hotkey']} unavailable"))
            if self.updated_launch and not self.hotkey_retry_scheduled:
                self.hotkey_retry_scheduled = True
                self.root.after(
                    1800,
                    lambda: threading.Thread(target=self.global_hotkey, daemon=True).start(),
                )
            return
        message = wintypes.MSG()
        self.root.after(0, lambda: self.status.config(text=f"Ready • {self.settings['hotkey']}"))
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    self.root.after(0, self.toggle_quick_launcher)
        finally:
            user32.UnregisterHotKey(None, 1)

    def toggle_quick_launcher(self):
        if self.closing:
            return
        if self.quick_window and self.quick_window.winfo_exists():
            self.close_quick_launcher()
            return

        c = self.palette()
        window = tk.Toplevel(self.root)
        self.quick_window = window
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=c["border"])
        window.geometry("620x70")
        window.update_idletasks()
        x = (window.winfo_screenwidth() - 620) // 2
        y = max(24, (window.winfo_screenheight() - 70) // 3)
        window.geometry(f"+{x}+{y}")
        window.bind("<Escape>", lambda event: self.close_quick_launcher())
        window.bind("<FocusOut>", self.on_quick_focus_out, add="+")

        content = tk.Frame(window, bg=c["panel"])
        content.pack(fill="both", expand=True, padx=1, pady=1)
        self.quick_search = tk.Entry(
            content, bg=c["panel"], fg=c["text"],
            insertbackground=c["accent"], font=("Segoe UI", 13),
            relief="flat", borderwidth=0,
        )
        self.quick_search.insert(0, "Search...")
        self.quick_search.config(fg=c["muted"])
        self.quick_search.bind("<FocusIn>", self.clear_quick_placeholder)
        self.quick_search.bind("<Return>", self.open_main_from_quick)
        self.quick_search.pack(
            side="left", fill="x", expand=True, padx=(16, 10), pady=19
        )
        tk.Frame(content, bg=c["border"], width=1).pack(
            side="left", fill="y", pady=13, padx=(0, 5)
        )

        self.quick_tab_buttons = {}
        for mode, icon in (
            ("apps", "▣"),
            ("favorites", "★"),
            ("files", "▤"),
            ("commands", "⌘"),
            ("tools", "∑"),
            ("settings", "⚙"),
        ):
            button = tk.Button(
                content, text=icon, command=lambda selected=mode: self.open_main_from_quick(mode=selected),
                bg=c["selected"] if mode == self.mode else c["panel"],
                fg=c["accent"] if mode == self.mode else c["muted"],
                activebackground=c["selected"], activeforeground=c["accent"],
                relief="flat", font=("Segoe UI Symbol", 13), width=2,
                takefocus=True, cursor="hand2", bd=0,
            )
            button.pack(side="left", padx=2, pady=10)
            self.quick_tab_buttons[mode] = button

        window.deiconify()
        window.lift()
        window.focus_force()
        self.quick_search.focus_force()

    def clear_quick_placeholder(self, event=None):
        if self.quick_search.get() == "Search...":
            self.quick_search.delete(0, "end")
            self.quick_search.config(fg=self.palette()["text"])

    def on_quick_focus_out(self, event=None):
        if self.quick_window and self.quick_window.winfo_exists():
            self.quick_window.after(180, self.close_quick_launcher_if_unfocused)

    def close_quick_launcher_if_unfocused(self):
        if not self.quick_window or not self.quick_window.winfo_exists():
            return
        try:
            focused = self.quick_window.focus_get()
        except tk.TclError:
            focused = None
        if focused is None or focused.winfo_toplevel() != self.quick_window:
            self.close_quick_launcher()

    def close_quick_launcher(self):
        if self.quick_window and self.quick_window.winfo_exists():
            self.quick_window.destroy()
        self.quick_window = None

    def open_main_from_quick(self, event=None, mode=None):
        if not self.quick_window or not self.quick_window.winfo_exists():
            return "break"
        query = self.quick_search.get().strip()
        if query == "Search...":
            query = ""
        selected_mode = mode or self.mode
        self.close_quick_launcher()
        if selected_mode != self.mode:
            self.change_mode(selected_mode)
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        if query and selected_mode != "settings":
            self.search.delete(0, "end")
            self.search.insert(0, query)
            self.on_search()
        self.root.after(120, self.focus_main_search)
        self.root.after(700, lambda: self.root.attributes("-topmost", False))
        return "break"

    def focus_main_search(self):
        if not self.closing:
            self.root.lift()
            if self.mode != "settings":
                self.search.focus_force()
                self.search.icursor("end")

    def scan_apps(self):
        found = {}
        folders = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        ]
        for folder in folders:
            if folder.exists():
                try:
                    for path in folder.rglob("*.lnk"):
                        found[path.stem.lower()] = (path.stem, str(path))
                except OSError:
                    pass
        for variable, default in (("PROGRAMFILES", "C:/Program Files"),
                                  ("PROGRAMFILES(X86)", "C:/Program Files (x86)")):
            folder = Path(os.environ.get(variable, default))
            if not folder.exists():
                continue
            try:
                for current, dirs, files in os.walk(folder):
                    dirs[:] = [name for name in dirs if name.lower() not in ("common files", "windowsapps")]
                    for filename in files:
                        if filename.lower().endswith(".exe"):
                            path = Path(current) / filename
                            found.setdefault(path.stem.lower(), (path.stem, str(path)))
            except OSError:
                pass
        self.apps = sorted(found.values(), key=lambda item: item[0].lower())
        if not self.closing:
            self.root.after(0, self.finish_scan)

    def finish_scan(self):
        if self.closing:
            return
        if self.mode in ("apps", "favorites"):
            self.search_apps()
        self.status.config(text=f"{len(self.apps)} applications detected")

    def update_tabs(self):
        c = self.palette()
        for mode, button in self.tab_buttons.items():
            active = mode == self.mode
            button.config(
                bg=c["selected"] if active else c["sidebar"],
                fg=c["accent"] if active else c["muted"],
                activebackground=c["selected"] if active else c["sidebar"],
                activeforeground=c["accent"] if active else c["text"],
            )

    def update_mode_panels(self):
        self.folder_frame.pack_forget()
        self.commands_frame.pack_forget()
        self.tools_frame.pack_forget()
        self.settings_frame.pack_forget()
        self.search_frame.pack_forget()
        self.status_row.pack_forget()
        self.result_outer.pack_forget()
        self.footer.pack_forget()
        if self.mode == "settings":
            self.settings_frame.pack(fill="both", expand=True)
            return
        if self.mode in ("apps", "favorites", "files", "commands", "tools"):
            self.search_frame.pack(fill="x", pady=(0, 9))
            if self.mode == "files":
                self.folder_frame.pack(fill="x", pady=5)
            elif self.mode == "commands":
                self.commands_frame.pack(fill="x", pady=3)
            elif self.mode == "tools":
                self.tools_frame.pack(fill="x", pady=3)
            self.status_row.pack(fill="x")
            self.result_outer.pack(fill="both", expand=True)
            self.footer.pack(fill="x", pady=(10, 0))
            self.favorite_button.pack_forget()
            self.remove_command_button.pack_forget()
            self.footer_hint.pack_forget()
            if self.mode in ("apps", "favorites"):
                self.favorite_button.pack(side="left")
            if self.mode == "commands":
                self.remove_command_button.pack(side="left", padx=6)
            self.footer_hint.pack(side="left", padx=12)

    def change_mode(self, mode):
        self.mode = mode
        headings = {
            "apps": ("Apps", "Find and launch something quickly."),
            "favorites": ("Favorites", "Your saved apps and shortcuts."),
            "files": ("Files", "Search files in a folder you choose."),
            "commands": ("Shortcuts", "Create quick links to websites and programs."),
            "tools": ("Tools", "Calculate safely or search the web."),
            "settings": ("Settings", "Tune CMD Pal to fit your workflow."),
        }
        title, subtitle = headings[mode]
        self.page_title_label.config(text=title)
        self.page_subtitle_label.config(text=subtitle)
        self.generation += 1
        self.search.delete(0, "end")
        self.results = []
        self.selected = 0
        children = self.listbox.get_children()
        if children:
            self.listbox.delete(*children)
        self.update_mode_panels()
        self.update_tabs()
        if mode in ("apps", "favorites"):
            self.search_apps()
        elif mode == "files":
            self.status.config(text="Type a filename to search")
        elif mode == "commands":
            self.search_commands()
        elif mode == "tools":
            self.status.config(text="Try 12 * (4 + 3), or enter text and choose SEARCH WEB.")
        self.search.focus_set() if mode != "settings" else None

    def choose_folder(self):
        selected = filedialog.askdirectory(
            title="Choose search folder",
            initialdir=str(self.folder if self.folder.exists() else Path.home()),
        )
        if selected:
            self.folder = Path(selected)
            self.folder_label.config(text="Folder: " + str(self.folder))
            if self.search.get().strip():
                self.search_files()

    def on_search(self, event=None):
        if self.mode in ("apps", "favorites"):
            self.search_apps()
        elif self.mode == "files":
            self.search_files()
        elif self.mode == "commands":
            self.search_commands()
        elif self.mode == "tools":
            self.calculate_query()

    def set_results(self, results):
        self.results = results[:100]
        self.selected = 0
        self.result_count_label.config(
            text=f"{len(self.results)} results" if self.results else ""
        )
        children = self.listbox.get_children()
        if children:
            self.listbox.delete(*children)
        self.result_images = []
        for index, (name, target, kind) in enumerate(self.results):
            image = None
            if self.settings["show_icons"]:
                image = self.result_icon(name, target, kind)
                self.result_images.append(image)
            favorite_mark = "★  " if target in self.settings["favorites"] else ""
            item_options = {
                "iid": str(index),
                "text": favorite_mark + name,
                "values": (self.result_kind_label(name, target, kind),),
            }
            if image is not None:
                item_options["image"] = image
            self.listbox.insert("", "end", **item_options)
        self.highlight_result()

    def result_kind_label(self, name, target, kind):
        if kind == "file":
            extension = Path(name).suffix.upper().lstrip(".")
            return extension or "FILE"
        return {
            "app": "APP", "command": "SHORTCUT", "hibernate": "SYSTEM",
            "result": "RESULT",
        }.get(kind, kind.upper())

    def result_icon(self, name, target, kind):
        icon_type = result_icon_type(
            name, target, kind, self.settings["custom_commands"]
        )
        key = (icon_type, self.palette()["panel"], self.palette()["accent"])
        if key in self.icon_cache:
            return self.icon_cache[key]

        c = self.palette()
        color = {
            "browser": "#75a7ff", "pdf": "#fb7474", "image": "#78c68b",
            "video": "#f0a75c", "audio": "#c18cff", "archive": "#d2ac70",
            "code": "#5fc2c2", "executable": "#77a9ff", "document": "#8faef1",
            "spreadsheet": "#63bd82", "presentation": "#ff9b72",
            "power": "#ff886e", "website": "#76a9ff",
        }.get(icon_type, c["accent"])
        image = tk.PhotoImage(master=self.root, width=20, height=20)
        image.put(c["panel"], to=(0, 0, 20, 20))

        def rectangle(x1, y1, x2, y2, fill):
            image.put(fill, to=(x1, y1, x2, y2))

        if icon_type in ("document", "pdf", "spreadsheet", "presentation"):
            rectangle(4, 2, 15, 18, color)
            rectangle(6, 4, 13, 16, c["panel"])
            rectangle(7, 7, 13, 8, color)
            rectangle(7, 10, 13, 11, color)
            rectangle(7, 13, 12, 14, color)
            if icon_type == "spreadsheet":
                rectangle(9, 6, 10, 15, color)
                rectangle(6, 9, 13, 10, color)
            elif icon_type == "presentation":
                rectangle(7, 6, 12, 7, color)
                rectangle(8, 8, 9, 12, color)
                rectangle(11, 8, 12, 12, color)
        elif icon_type == "image":
            rectangle(2, 4, 18, 17, color)
            rectangle(4, 6, 16, 15, c["panel"])
            rectangle(6, 8, 9, 11, "#ffc46b")
            for x, y in ((4, 14), (5, 13), (6, 12), (7, 11), (8, 12),
                         (9, 13), (10, 12), (11, 11), (12, 12), (13, 13),
                         (14, 14), (15, 14)):
                rectangle(x, y, x + 1, y + 1, color)
        elif icon_type in ("browser", "website"):
            for y in range(2, 18):
                for x in range(2, 18):
                    if (x - 10) ** 2 + (y - 10) ** 2 <= 64:
                        image.put(color, to=(x, y))
            for x, y in ((7, 5), (8, 4), (9, 3), (10, 3), (11, 4),
                         (12, 5), (7, 14), (8, 15), (9, 16), (10, 16),
                         (11, 15), (12, 14)):
                rectangle(x, y, x + 1, y + 1, c["panel"])
            rectangle(3, 9, 17, 11, c["panel"])
            rectangle(9, 3, 11, 17, c["panel"])
        elif icon_type == "video":
            rectangle(2, 4, 18, 16, color)
            for x, y in ((8, 7), (9, 8), (10, 9), (11, 10),
                         (10, 11), (9, 12), (8, 13)):
                rectangle(x, y, x + 1, y + 1, c["panel"])
        elif icon_type == "audio":
            for x, top, bottom in ((3, 8, 12), (6, 5, 15), (9, 2, 18),
                                   (12, 5, 15), (15, 8, 12)):
                rectangle(x, top, x + 2, bottom, color)
        elif icon_type == "archive":
            rectangle(4, 2, 16, 18, color)
            rectangle(8, 2, 12, 18, c["panel"])
            for y in (4, 7, 10, 13):
                rectangle(8, y, 12, y + 1, color)
        elif icon_type == "code":
            for x, y in ((7, 5), (6, 6), (5, 7), (4, 8), (5, 9), (6, 10),
                         (13, 5), (14, 6), (15, 7), (16, 8), (15, 9), (14, 10),
                         (11, 4), (10, 7), (9, 10), (8, 13)):
                rectangle(x, y, x + 2, y + 2, color)
        elif icon_type == "power":
            for x, y in ((9, 2), (9, 4), (9, 6), (5, 5), (4, 7), (3, 9),
                         (3, 11), (4, 13), (6, 15), (8, 16), (11, 16),
                         (14, 15), (16, 13), (17, 11), (16, 8), (14, 6)):
                rectangle(x, y, x + 2, y + 2, color)
        elif icon_type == "calculator":
            rectangle(3, 2, 17, 18, color)
            rectangle(5, 4, 15, 7, c["panel"])
            for x, y in ((5, 9), (10, 9), (5, 13), (10, 13)):
                rectangle(x, y, x + 3, y + 2, c["panel"])
        else:
            rectangle(3, 3, 17, 17, color)
            rectangle(5, 5, 15, 7, c["panel"])
            rectangle(5, 9, 15, 10, c["panel"])
            rectangle(5, 12, 12, 13, c["panel"])

        self.icon_cache[key] = image
        return image

    def search_apps(self):
        query = self.search.get().strip().lower()
        found = {path: (name, path, "app") for name, path in self.apps}
        custom = self.settings["custom_commands"]
        for command in custom:
            target = self.command_key(command)
            found[target] = (command["name"], target, "command")

        if self.mode == "favorites":
            ordered = [found[path] for path in self.settings["favorites"] if path in found]
        else:
            ordered = []
            if not query:
                for path_list in (self.settings["favorites"], self.settings["recent"]):
                    for path in path_list:
                        if path in found and found[path] not in ordered:
                            ordered.append(found[path])
            ordered.extend(item for item in found.values() if item not in ordered)
        matches = [item for item in ordered if not query or query in item[0].lower()]
        if query == "h":
            matches.insert(0, ("Hibernate • Windows power command", HIBERNATE_COMMAND, "hibernate"))
        self.set_results(matches[:50])
        self.status.config(text=f"{len(self.results)} options found" if self.results
                           else "No matching applications or shortcuts")

    def command_key(self, command):
        return "cmdpal:" + command["type"] + ":" + command["name"]

    def search_commands(self):
        query = self.search.get().strip().lower()
        matches = []
        for command in self.settings["custom_commands"]:
            if query in command["name"].lower() or query in command["target"].lower():
                matches.append((command["name"], self.command_key(command), "command"))
        self.set_results(matches)
        self.status.config(text=f"{len(matches)} shortcuts" if matches else "No matching shortcuts")

    def add_custom_command(self):
        name = self.command_name.get().strip()
        target = self.command_target.get().strip()
        kind = "website" if self.command_type.get() == "Website" else "program"
        if not name or not target:
            self.status.config(text="Enter a shortcut name and target.")
            return
        if kind == "website":
            parsed = urlparse(target)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                self.status.config(text="Website shortcuts must use a full http:// or https:// URL.")
                return
        elif not Path(target).is_file():
            self.status.config(text="Choose an existing program file.")
            return
        self.settings["custom_commands"] = [
            command for command in self.settings["custom_commands"]
            if command["name"].lower() != name.lower()
        ]
        self.settings["custom_commands"].append({"name": name, "target": target, "type": kind})
        saved = self.save_settings()
        self.command_name.delete(0, "end")
        self.command_target.delete(0, "end")
        self.search_commands()
        self.status.config(text="Shortcut added." if saved else "Shortcut added, but could not be saved.")

    def remove_custom_command(self):
        if not self.results or self.selected >= len(self.results):
            return
        _, key, kind = self.results[self.selected]
        if kind != "command":
            return
        self.settings["custom_commands"] = [
            command for command in self.settings["custom_commands"]
            if self.command_key(command) != key
        ]
        self.settings["favorites"] = [path for path in self.settings["favorites"] if path != key]
        self.settings["recent"] = [path for path in self.settings["recent"] if path != key]
        saved = self.save_settings()
        self.search_commands()
        self.status.config(text="Shortcut removed." if saved else "Shortcut removed, but could not be saved.")

    def search_files(self):
        query = self.search.get().strip().lower()
        self.generation += 1
        generation = self.generation
        self.set_results([])
        if not query:
            self.status.config(text="Type a filename to search")
            return
        self.status.config(text="Searching selected folder...")
        threading.Thread(target=self.file_worker, args=(query, generation), daemon=True).start()

    def file_worker(self, query, generation):
        matches = []
        try:
            for current, dirs, files in os.walk(self.folder):
                if generation != self.generation:
                    return
                dirs[:] = [name for name in dirs if name.lower() not in
                           ("$recycle.bin", "system volume information", "__pycache__")]
                for filename in files:
                    if query in filename.lower():
                        matches.append((filename, str(Path(current) / filename), "file"))
                        if len(matches) >= 100:
                            break
                if len(matches) >= 100:
                    break
        except OSError as error:
            if not self.closing:
                self.root.after(
                    0, lambda error=error: self.status.config(
                        text=f"Could not search folder: {error}"
                    )
                )
            return
        if not self.closing:
            self.root.after(0, lambda: self.show_files(matches, generation))

    def show_files(self, matches, generation):
        if self.closing or generation != self.generation or self.mode != "files":
            return
        self.set_results(matches)
        self.status.config(text=f"{len(matches)} matching files" if matches else "No matching files found")

    def calculate_query(self):
        expression = self.search.get().strip()
        if not expression:
            self.set_results([])
            self.status.config(text="Enter an arithmetic expression.")
            return
        try:
            result = calculate(expression)
        except (ValueError, SyntaxError) as error:
            self.set_results([])
            self.status.config(text=str(error))
            return
        self.set_results([(f"{expression} = {result}", "", "result")])
        self.status.config(text="Calculation complete")

    def search_web(self):
        query = self.search.get().strip()
        if not query:
            self.status.config(text="Enter a web search query first.")
            return
        try:
            opened = webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
            self.status.config(text="Opened web search in your browser." if opened
                               else "Could not find a browser to open the web search.")
        except OSError as error:
            self.status.config(text=f"Could not open web search: {error}")

    def highlight_result(self):
        selection = self.listbox.selection()
        if selection:
            self.listbox.selection_remove(*selection)
        if self.results:
            item = str(self.selected)
            self.listbox.selection_set(item)
            self.listbox.focus(item)
            self.listbox.see(item)

    def on_tree_select(self, event=None):
        selection = self.listbox.selection()
        if selection:
            self.selected = int(selection[0])

    def move_up(self, event=None):
        if self.results:
            self.selected = max(0, self.selected - 1)
            self.highlight_result()
        return "break"

    def move_down(self, event=None):
        if self.results:
            self.selected = min(len(self.results) - 1, self.selected + 1)
            self.highlight_result()
        return "break"

    def toggle_favorite(self, event=None):
        if self.mode not in ("apps", "favorites") or not self.results:
            return "break"
        _, target, kind = self.results[self.selected]
        if kind not in ("app", "command"):
            return "break"
        favorites = self.settings["favorites"]
        if target in favorites:
            favorites.remove(target)
            message = "Removed from favorites."
        else:
            favorites.insert(0, target)
            message = "Added to favorites."
        saved = self.save_settings()
        self.search_apps()
        self.status.config(text=message if saved else message + " Could not save settings.")
        return "break"

    def remember_recent(self, target):
        recent = self.settings["recent"]
        self.settings["recent"] = [target] + [item for item in recent if item != target]
        self.settings["recent"] = self.settings["recent"][:10]
        self.save_settings()

    def launch_selected(self, event=None):
        if not self.results:
            return "break"
        name, target, kind = self.results[self.selected]
        try:
            if kind == "result":
                return "break"
            if kind == "hibernate":
                if os.name != "nt":
                    self.status.config(text="Hibernate is only available on Windows")
                    return "break"
                subprocess.Popen(
                    ["shutdown.exe", "/h"], shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            elif kind == "command":
                command = next(item for item in self.settings["custom_commands"]
                               if self.command_key(item) == target)
                if command["type"] == "website":
                    parsed = urlparse(command["target"])
                    if parsed.scheme not in ("http", "https") or not parsed.netloc:
                        raise ValueError("Shortcut URL must use http:// or https://.")
                    if not webbrowser.open(command["target"]):
                        raise OSError("Could not find a browser to open this shortcut.")
                else:
                    self.open_path(command["target"])
                self.remember_recent(target)
            elif kind == "file":
                self.open_path(target)
            else:
                self.open_path(target)
                self.remember_recent(target)
            self.status.config(text=f"Opening {name}...")
        except (OSError, ValueError, StopIteration) as error:
            self.status.config(text=f"Could not open {name}: {error}")
        return "break"

    def open_path(self, path):
        if os.name == "nt":
            if Path(path).suffix.lower() == ".exe":
                subprocess.Popen(
                    [path], shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                os.startfile(path)
        else:
            subprocess.Popen([path], shell=False, creationflags=0)

    def clear(self, event=None):
        self.search.delete(0, "end")
        if self.mode in ("apps", "favorites"):
            self.search_apps()
        elif self.mode == "files":
            self.search_files()
        elif self.mode == "commands":
            self.search_commands()
        elif self.mode == "tools":
            self.set_results([])
            self.status.config(text="Enter an expression or a web search.")
        return "break"

    def close(self):
        self.closing = True
        self.close_quick_launcher()
        if self.hotkey_thread_id and os.name == "nt":
            try:
                ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, 0x0012, 0, 0)
            except OSError:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    CMDPal().run()
