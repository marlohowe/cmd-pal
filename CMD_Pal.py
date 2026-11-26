import ast
import ctypes
import json
import math
import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog, ttk
from urllib.parse import quote_plus, urlparse


BG = "#0c0e16"
PANEL = "#191f2c"
ACCENT = "#75f0ad"
TEXT = "#f4f6ff"
MUTED = "#929db0"
SELECTED = "#234b3b"
HIBERNATE_COMMAND = "__CMD_HIBERNATE__"


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


class CMDPal:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CMD Pal")
        self.root.geometry("820x620")
        self.root.minsize(650, 480)
        self.root.configure(bg=BG)

        self.mode = "apps"
        self.folder = Path.home()
        self.apps = []
        self.results = []
        self.selected = 0
        self.generation = 0
        self.hotkey_thread_id = None
        self.closing = False
        self.config_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "CMDPal" / "settings.json"
        self.settings = {
            "theme": "dark",
            "hotkey": "Shift+?",
            "favorites": [],
            "recent": [],
            "custom_commands": [],
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

    def palette(self):
        if self.settings["theme"] == "light":
            return {
                "bg": "#f3f5fa", "panel": "#ffffff", "accent": "#176b4b",
                "text": "#182235", "muted": "#647084", "selected": "#d5eee2",
            }
        return {"bg": BG, "panel": PANEL, "accent": ACCENT,
                "text": TEXT, "muted": MUTED, "selected": SELECTED}

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
        self.gradient_image = self.gradient(820, 90)
        tk.Label(self.root, image=self.gradient_image, borderwidth=0).pack(fill="x")
        heading = tk.Frame(self.root, bg=BG)
        heading.pack(fill="x", padx=25, pady=(8, 2))
        tk.Label(heading, text="CMD PAL", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(heading, text="Your personal launcher", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")

        tabs = tk.Frame(self.root, bg=BG)
        tabs.pack(fill="x", padx=25, pady=7)
        self.tab_buttons = {}
        for mode, title in (
            ("apps", "APPS"), ("favorites", "FAVORITES"), ("files", "FILES"),
            ("commands", "COMMANDS"), ("tools", "TOOLS"), ("settings", "SETTINGS"),
        ):
            button = tk.Button(
                tabs, text=title, command=lambda selected=mode: self.change_mode(selected),
                font=("Segoe UI", 9, "bold"), relief="flat", padx=9, pady=8,
                cursor="hand2",
            )
            button.pack(side="left", padx=(0, 5))
            self.tab_buttons[mode] = button

        self.search_frame = tk.Frame(self.root, bg=PANEL, highlightthickness=1,
                                     highlightbackground="#344153")
        self.search_frame.pack(fill="x", padx=25, pady=7)
        tk.Label(self.search_frame, text="⌕", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 20)).pack(side="left", padx=10)
        self.search = tk.Entry(self.search_frame, bg=PANEL, fg=TEXT,
                               insertbackground=ACCENT, font=("Segoe UI", 14),
                               relief="flat", borderwidth=0)
        self.search.pack(side="left", fill="x", expand=True, padx=8, pady=13)
        self.search.bind("<KeyRelease>", self.on_search)

        self.folder_frame = tk.Frame(self.root, bg=BG)
        self.folder_label = tk.Label(self.folder_frame, text="Folder: " + str(self.folder),
                                     bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True)
        tk.Button(self.folder_frame, text="Choose Folder", command=self.choose_folder,
                  bg=PANEL, fg=ACCENT, relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=10, pady=6).pack(side="right")

        self.commands_frame = tk.Frame(self.root, bg=BG)
        self.build_commands_controls()
        self.tools_frame = tk.Frame(self.root, bg=BG)
        self.build_tools_controls()
        self.status = tk.Label(self.root, text="Loading applications...", bg=BG,
                               fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", padx=29, pady=6)

        self.result_outer = tk.Frame(self.root, bg="#344153", padx=1, pady=1)
        self.result_outer.pack(fill="both", expand=True, padx=25, pady=(0, 10))
        inner = tk.Frame(self.result_outer, bg=PANEL)
        inner.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(inner, bg=PANEL, fg=TEXT, selectbackground=SELECTED,
                                  selectforeground=ACCENT, font=("Segoe UI", 11),
                                  relief="flat", borderwidth=0, highlightthickness=0,
                                  activestyle="none", exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)
        self.listbox.bind("<Double-Button-1>", self.launch_selected)

        self.footer = tk.Frame(self.root, bg=BG)
        self.footer.pack(fill="x", padx=25, pady=(0, 10))
        self.favorite_button = tk.Button(
            self.footer, text="☆ Favorite  (Ctrl+D)", command=self.toggle_favorite,
            bg=PANEL, fg=ACCENT, relief="flat", font=("Segoe UI", 8, "bold"),
            padx=8, pady=5,
        )
        self.favorite_button.pack(side="left")
        self.remove_command_button = tk.Button(
            self.footer, text="Remove command", command=self.remove_custom_command,
            bg=PANEL, fg=ACCENT, relief="flat", font=("Segoe UI", 8, "bold"),
            padx=8, pady=5,
        )
        self.remove_command_button.pack(side="left", padx=6)
        tk.Label(self.footer, text="↑ ↓ Navigate   ENTER Open   ESC Clear",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10)
        self.hotkey_label = tk.Label(self.footer, text=self.settings["hotkey"].upper(),
                                     bg=BG, fg=ACCENT, font=("Segoe UI", 8, "bold"))
        self.hotkey_label.pack(side="right")

        self.settings_frame = tk.Frame(self.root, bg=BG)
        self.build_settings_ui()
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
        tk.Label(self.settings_frame, text="Settings", font=("Segoe UI", 20, "bold"),
                 bg=c["bg"], fg=c["accent"]).pack(anchor="w", pady=(5, 10))
        tk.Label(self.settings_frame, text="Appearance", font=("Segoe UI", 11, "bold"),
                 bg=c["bg"], fg=c["text"]).pack(anchor="w")
        self.theme_var = tk.StringVar(value=self.settings["theme"].title())
        theme_row = tk.Frame(self.settings_frame, bg=c["bg"])
        theme_row.pack(anchor="w", pady=3)
        for label in ("Dark", "Light"):
            tk.Radiobutton(theme_row, text=label, value=label, variable=self.theme_var,
                           bg=c["bg"], fg=c["text"], selectcolor=c["panel"],
                           activebackground=c["bg"]).pack(side="left", padx=(0, 10))

        tk.Label(self.settings_frame, text="Global launch shortcut",
                 font=("Segoe UI", 11, "bold"), bg=c["bg"], fg=c["text"]
                 ).pack(anchor="w", pady=(8, 0))
        self.hotkey_var = tk.StringVar(value=self.settings["hotkey"])
        tk.Entry(self.settings_frame, textvariable=self.hotkey_var, width=25,
                 font=("Segoe UI", 10), bg=c["panel"], fg=c["text"],
                 insertbackground=c["accent"]).pack(anchor="w", pady=4, ipady=3)
        tk.Label(self.settings_frame, text="Default: Shift+?   |   Example: Ctrl+Alt+K",
                 bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8)).pack(anchor="w")

        tk.Label(self.settings_frame, text="Run a Windows .exe installer",
                 font=("Segoe UI", 12, "bold"), bg=c["bg"], fg=c["accent"]
                 ).pack(anchor="w", pady=(12, 2))
        row = tk.Frame(self.settings_frame, bg=c["bg"])
        row.pack(fill="x", pady=4)
        self.installer_var = tk.StringVar(value="No installer selected")
        tk.Entry(row, textvariable=self.installer_var, state="readonly",
                 bg=c["panel"], fg=c["text"], readonlybackground=c["panel"]
                 ).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(row, text="Browse .EXE", command=self.choose_installer,
                  bg=c["panel"], fg=c["accent"], relief="flat", padx=8, pady=5
                  ).pack(side="left", padx=(6, 0))
        tk.Button(self.settings_frame, text="RUN INSTALLER", command=self.run_installer,
                  bg=c["accent"], fg=c["bg"], relief="flat", padx=12, pady=7
                  ).pack(anchor="w")
        self.installer_status = tk.Label(self.settings_frame, text="", bg=c["bg"],
                                         fg=c["muted"], font=("Segoe UI", 8))
        self.installer_status.pack(anchor="w", pady=2)
        self.selected_installer = None
        self.settings_message = tk.Label(self.settings_frame, text="", bg=c["bg"], fg=c["muted"])
        self.settings_message.pack(anchor="w", pady=(7, 2))
        tk.Button(self.settings_frame, text="SAVE SETTINGS", command=self.apply_settings,
                  bg=c["accent"], fg=c["bg"], relief="flat", padx=12, pady=7
                  ).pack(anchor="w")

    def load_settings(self):
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return
                if data.get("theme") in ("dark", "light"):
                    self.settings["theme"] = data["theme"]
                if isinstance(data.get("hotkey"), str):
                    self.settings["hotkey"] = data["hotkey"]
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
        self.settings["theme"] = self.theme_var.get().lower()
        self.settings["hotkey"] = shortcut
        saved = self.save_settings()
        self.apply_theme()
        self.hotkey_label.config(text=shortcut.upper())
        if os.name == "nt":
            self.restart_hotkey()
        self.settings_message.config(text="Settings saved." if saved else
                                     "Settings applied, but could not be saved.")

    def apply_theme(self):
        c = self.palette()
        mapping = {BG: c["bg"], PANEL: c["panel"], ACCENT: c["accent"],
                   TEXT: c["text"], MUTED: c["muted"], SELECTED: c["selected"],
                   "#344153": c["panel"]}

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
            return
        message = wintypes.MSG()
        self.root.after(0, lambda: self.status.config(text=f"Ready • {self.settings['hotkey']}"))
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    self.root.after(0, self.toggle_window)
        finally:
            user32.UnregisterHotKey(None, 1)

    def toggle_window(self):
        if self.closing:
            return
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(120, self.focus_search)
            self.root.after(700, lambda: self.root.attributes("-topmost", False))
        else:
            self.root.withdraw()

    def focus_search(self):
        if not self.closing:
            self.root.lift()
            self.root.focus_force()
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
            button.config(bg=c["accent"] if active else c["panel"],
                          fg=c["bg"] if active else c["text"])

    def update_mode_panels(self):
        self.folder_frame.pack_forget()
        self.commands_frame.pack_forget()
        self.tools_frame.pack_forget()
        self.settings_frame.pack_forget()
        self.search_frame.pack_forget()
        self.status.pack_forget()
        self.result_outer.pack_forget()
        self.footer.pack_forget()
        if self.mode == "settings":
            self.settings_frame.pack(fill="both", expand=True, padx=25, pady=8)
            return
        if self.mode in ("apps", "favorites", "files", "commands", "tools"):
            self.search_frame.pack(fill="x", padx=25, pady=7)
            if self.mode == "files":
                self.folder_frame.pack(fill="x", padx=25, pady=5)
            elif self.mode == "commands":
                self.commands_frame.pack(fill="x", padx=25, pady=3)
            elif self.mode == "tools":
                self.tools_frame.pack(fill="x", padx=25, pady=3)
            self.status.pack(fill="x", padx=29, pady=5)
            self.result_outer.pack(fill="both", expand=True, padx=25, pady=(0, 10))
            self.footer.pack(fill="x", padx=25, pady=(0, 10))
            self.favorite_button.pack_forget()
            self.remove_command_button.pack_forget()
            if self.mode in ("apps", "favorites"):
                self.favorite_button.pack(side="left")
            if self.mode == "commands":
                self.remove_command_button.pack(side="left", padx=6)

    def change_mode(self, mode):
        self.mode = mode
        self.generation += 1
        self.search.delete(0, "end")
        self.results = []
        self.selected = 0
        self.listbox.delete(0, "end")
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
        self.listbox.delete(0, "end")
        for name, target, kind in self.results:
            mark = "★ " if target in self.settings["favorites"] else ""
            self.listbox.insert("end", "   " + mark + name)
        self.highlight_result()

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
        self.listbox.selection_clear(0, "end")
        if self.results:
            self.listbox.selection_set(self.selected)
            self.listbox.activate(self.selected)
            self.listbox.see(self.selected)

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
                subprocess.Popen(["shutdown.exe", "/h"], shell=False)
            elif kind == "command":
                command = next(item for item in self.settings["custom_commands"]
                               if self.command_key(item) == target)
                if command["type"] == "website":
                    parsed = urlparse(command["target"])
                    if parsed.scheme not in ("http", "https") or not parsed.netloc:
                        raise ValueError("Shortcut URL must use http:// or https://.")
                    if not webbrowser.open(command["target"]):
                        raise OSError("Could not find a browser to open this shortcut.")
                elif os.name == "nt":
                    os.startfile(command["target"])
                else:
                    subprocess.Popen([command["target"]], shell=False)
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
            os.startfile(path)
        else:
            subprocess.Popen([path], shell=False)

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
