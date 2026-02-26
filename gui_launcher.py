"""
Twitch Viewer Bot — GUI Launcher
A user-friendly graphical interface for non-technical users.
No extra dependencies beyond Python's built-in tkinter.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import os
import sys
import ctypes
import struct
import requests
import threading
import subprocess
import shutil

# ── Ensure project root is on path ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_engine import (
    PROXY_SERVERS, ViewerBot, fetch_proxies_from_url
)  # noqa: E402

# ─── Color palette ──────────────────────────────────────────────────────
BG_DARK      = "#0e0b16"
BG_PANEL     = "#1a1333"
BG_INPUT     = "#2a1f4e"
BG_INFO      = "#1c2a1c"
FG_TEXT       = "#e0d7ff"
FG_DIM        = "#8a82a6"
ACCENT        = "#9147ff"   # Twitch purple
ACCENT_HOVER  = "#b380ff"
SUCCESS       = "#2ecc71"
DANGER        = "#e74c3c"
WARN_BG       = "#2a2a1c"
WARN_BORDER   = "#6b6b2d"
INFO_BORDER   = "#2d6b2d"
BTN_SETUP     = "#3d2d6b"
BTN_SETUP_HVR = "#5a45a0"

# ─── RAM detection (Windows, zero dependencies) ────────────────────────
MB_PER_INSTANCE = 150  # each viewer = separate Chrome process (~150 MB)
RAM_USAGE_RATIO = 0.60  # use at most 60% of *available* RAM


def get_system_ram():
    """Return (total_mb, available_mb) using Windows GlobalMemoryStatusEx."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_mb = stat.ullTotalPhys / (1024 * 1024)
        avail_mb = stat.ullAvailPhys / (1024 * 1024)
        return int(total_mb), int(avail_mb)
    except Exception:
        return None, None


def suggest_viewers(avail_mb):
    """Recommend a viewer count based on available RAM."""
    if avail_mb is None:
        return 10  # safe fallback
    usable = int(avail_mb * RAM_USAGE_RATIO)
    suggested = max(3, usable // MB_PER_INSTANCE)
    return min(suggested, 50)  # hard cap for separate instances


def max_viewers(avail_mb):
    """Absolute max viewers before likely OOM."""
    if avail_mb is None:
        return 30
    return max(5, int(avail_mb * 0.80) // MB_PER_INSTANCE)


# ─── Environment checks ────────────────────────────────────────────────
def check_python():
    """Return (installed: bool, version: str)."""
    try:
        ver = sys.version.split()[0]
        return True, ver
    except Exception:
        return False, ""


def check_pip_packages():
    """Return (all_ok: bool, missing: list[str])."""
    required = ["selenium", "colorama", "pystyle", "requests", "webdriver_manager"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return len(missing) == 0, missing


def check_chromedriver():
    """Return (installed: bool, path_or_msg: str)."""
    # Check local project dir first
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver.exe")
    if os.path.isfile(local):
        return True, local
    # Check PATH
    found = shutil.which("chromedriver")
    if found:
        return True, found
    # Check webdriver-manager cache
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        path = ChromeDriverManager().install()
        if path and os.path.isfile(path):
            return True, path
    except Exception:
        pass
    return False, "Not found"


class TwitchBotGUI(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("Twitch Viewer Bot")
        self.geometry("560x1060")
        self.resizable(False, False)
        self.configure(bg=BG_DARK)

        self.bot = None
        self.total_mb, self.avail_mb = get_system_ram()
        self.suggested = suggest_viewers(self.avail_mb)
        self.viewer_max = max_viewers(self.avail_mb)
        self._build_ui()

    # ── UI construction ─────────────────────────────────────────────────
    def _build_ui(self):
        # Title banner
        banner = tk.Frame(self, bg=BG_DARK)
        banner.pack(fill="x", pady=(18, 4))
        tk.Label(
            banner, text="⚡  Twitch Viewer Bot", font=("Segoe UI", 20, "bold"),
            fg=ACCENT, bg=BG_DARK
        ).pack()
        tk.Label(
            banner, text="Easy setup — no command line needed",
            font=("Segoe UI", 10), fg=FG_DIM, bg=BG_DARK
        ).pack()

        # ── Setup Tools card ─────────────────────────────────────────────
        self._build_setup_card()

        # ── Settings card ───────────────────────────────────────────────
        card = tk.Frame(self, bg=BG_PANEL, bd=0, highlightthickness=1,
                        highlightbackground="#3d2d6b")
        card.pack(fill="x", padx=28, pady=(14, 8))

        # --- Proxy selector ---
        tk.Label(card, text="PROXY SERVER", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG_PANEL, anchor="w").pack(fill="x", padx=16, pady=(14, 2))

        self.proxy_var = tk.StringVar()
        proxy_options = []
        for pid, (name, url) in PROXY_SERVERS.items():
            label = f"Proxy {pid} — {name}"
            if pid == 1:
                label += "  ★ Recommended"
            proxy_options.append(label)

        self.proxy_combo = ttk.Combobox(
            card, textvariable=self.proxy_var, values=proxy_options,
            state="readonly", font=("Segoe UI", 11)
        )
        self.proxy_combo.current(0)
        self.proxy_combo.pack(fill="x", padx=16, pady=(0, 4))

        # Auto-rotate checkbox
        self.rotate_var = tk.BooleanVar(value=True)
        rotate_cb = tk.Checkbutton(
            card, text="Auto-rotate: cycle healthy proxies "
            "for each viewer",
            variable=self.rotate_var,
            font=("Segoe UI", 9), fg=FG_TEXT,
            bg=BG_PANEL, selectcolor=BG_INPUT,
            activebackground=BG_PANEL,
            activeforeground=FG_TEXT,
            anchor="w", cursor="hand2"
        )
        rotate_cb.pack(fill="x", padx=16, pady=(0, 10))

        # --- Channel name ---
        tk.Label(card, text="CHANNEL NAME", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG_PANEL, anchor="w").pack(fill="x", padx=16, pady=(6, 2))

        self.channel_entry = tk.Entry(
            card, font=("Segoe UI", 13), bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#3d2d6b",
            highlightcolor=ACCENT
        )
        self.channel_entry.insert(0, "")
        self.channel_entry.pack(fill="x", padx=16, pady=(0, 4), ipady=6)

        # placeholder behaviour
        self._add_placeholder(self.channel_entry, "e.g. kichi779")

        # ── RAM info bar ─────────────────────────────────────────────
        ram_frame = tk.Frame(card, bg=BG_INFO, bd=0,
                             highlightthickness=1, highlightbackground=INFO_BORDER)
        ram_frame.pack(fill="x", padx=16, pady=(10, 6))

        if self.total_mb and self.avail_mb:
            total_gb = round(self.total_mb / 1024, 1)
            avail_gb = round(self.avail_mb / 1024, 1)
            ram_text = (f"🖥  RAM: {avail_gb} GB free / {total_gb} GB total")
            rec_text = (f"✅  Recommended: ~{self.suggested} viewers  "
                        f"(max safe: ~{self.viewer_max})")
        else:
            ram_text = "🖥  RAM: could not detect"
            rec_text = "⚠  Defaulting to 30 viewers"

        tk.Label(ram_frame, text=ram_text,
                 font=("Segoe UI", 9, "bold"), fg=SUCCESS, bg=BG_INFO,
                 anchor="w").pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(ram_frame, text=rec_text,
                 font=("Segoe UI", 9), fg="#a3d9a5", bg=BG_INFO,
                 anchor="w").pack(fill="x", padx=10, pady=(0, 6))

        # --- Viewer count ---
        tk.Label(card, text="NUMBER OF VIEWERS", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG_PANEL, anchor="w").pack(fill="x", padx=16, pady=(10, 2))

        slider_frame = tk.Frame(card, bg=BG_PANEL)
        slider_frame.pack(fill="x", padx=16, pady=(0, 14))

        self.viewer_var = tk.IntVar(value=self.suggested)
        self.viewer_label = tk.Label(
            slider_frame, text=str(self.suggested),
            font=("Segoe UI", 16, "bold"),
            fg=ACCENT, bg=BG_PANEL, width=4
        )
        self.viewer_label.pack(side="left")

        self.viewer_scale = tk.Scale(
            slider_frame, from_=5, to=self.viewer_max,
            orient="horizontal",
            variable=self.viewer_var, bg=BG_PANEL, fg=FG_TEXT,
            highlightbackground=BG_PANEL, troughcolor=BG_INPUT,
            activebackground=ACCENT, sliderrelief="flat",
            showvalue=False, command=self._on_slider
        )
        self.viewer_scale.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # tip
        tk.Label(card, text="\U0001f4a1 Tip: set ~50% more than desired (e.g. 30 to get ~20)",
                 font=("Segoe UI", 8), fg=FG_DIM, bg=BG_PANEL,
                 anchor="w").pack(fill="x", padx=16, pady=(0, 12))

        # ── Proxy management card ────────────────────────────────────────
        self._build_proxy_card()

        # ── Action buttons ──────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=BG_DARK)
        btn_frame.pack(fill="x", padx=28, pady=(8, 4))

        self.launch_btn = tk.Button(
            btn_frame, text="▶  Launch Bot", font=("Segoe UI", 13, "bold"),
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_launch, bd=0
        )
        self.launch_btn.pack(fill="x", ipady=10)

        self.stop_btn = tk.Button(
            btn_frame, text="■  Stop Bot", font=("Segoe UI", 11, "bold"),
            bg=DANGER, fg="white", activebackground="#c0392b",
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_stop, bd=0, state="disabled"
        )
        self.stop_btn.pack(fill="x", ipady=6, pady=(6, 0))

        # ── Status log ──────────────────────────────────────────────────
        tk.Label(self, text="STATUS LOG", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG_DARK, anchor="w").pack(fill="x", padx=28, pady=(12, 2))

        self.log_box = scrolledtext.ScrolledText(
            self, height=10, font=("Consolas", 9), bg=BG_PANEL, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#3d2d6b",
            state="disabled", wrap="word"
        )
        self.log_box.pack(fill="both", expand=True, padx=28, pady=(0, 14))

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            self, textvariable=self.status_var,
            font=("Segoe UI", 9), fg=SUCCESS, bg=BG_DARK, anchor="w"
        )
        status_bar.pack(fill="x", padx=28, pady=(0, 8))

        # Theme the combobox dropdown
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=BG_INPUT, background=BG_INPUT,
                        foreground=FG_TEXT, arrowcolor=ACCENT,
                        bordercolor="#3d2d6b", lightcolor=BG_INPUT,
                        darkcolor=BG_INPUT)

    # ── Setup Tools card ────────────────────────────────────────────────
    def _build_setup_card(self):
        """Build the collapsible setup/install panel."""
        wrapper = tk.Frame(self, bg=BG_DARK)
        wrapper.pack(fill="x", padx=28, pady=(4, 4))

        # Toggle header
        self._setup_open = tk.BooleanVar(value=False)
        toggle_btn = tk.Button(
            wrapper, text="🔧  Setup Tools  ▼",
            font=("Segoe UI", 10, "bold"), fg=FG_DIM, bg=BG_PANEL,
            activebackground=BG_INPUT, activeforeground=FG_TEXT,
            relief="flat", bd=0, cursor="hand2",
            command=lambda: self._toggle_setup()
        )
        toggle_btn.pack(fill="x", ipady=4)
        self._setup_toggle_btn = toggle_btn

        # Collapsible body
        self._setup_body = tk.Frame(wrapper, bg=BG_PANEL, bd=0,
                                    highlightthickness=1,
                                    highlightbackground="#3d2d6b")
        # Starts hidden

        # --- Python row ---
        py_ok, py_ver = check_python()
        row1 = tk.Frame(self._setup_body, bg=BG_PANEL)
        row1.pack(fill="x", padx=12, pady=(10, 4))

        self._py_status = tk.Label(
            row1, text=f"✅ Python {py_ver}" if py_ok else "❌ Python not found",
            font=("Segoe UI", 9), fg=SUCCESS if py_ok else DANGER,
            bg=BG_PANEL, anchor="w"
        )
        self._py_status.pack(side="left", fill="x", expand=True)

        self._py_btn = tk.Button(
            row1, text="Install Python",
            font=("Segoe UI", 9, "bold"), fg=FG_TEXT, bg=BTN_SETUP,
            activebackground=BTN_SETUP_HVR, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=12,
            command=self._install_python
        )
        self._py_btn.pack(side="right")
        if py_ok:
            self._py_btn.config(state="disabled", text="Installed ✔")

        # --- Requirements row ---
        pkgs_ok, pkgs_missing = check_pip_packages()
        row2 = tk.Frame(self._setup_body, bg=BG_PANEL)
        row2.pack(fill="x", padx=12, pady=4)

        if pkgs_ok:
            req_label = "✅ All packages installed"
        else:
            req_label = f"❌ Missing: {', '.join(pkgs_missing)}"

        self._req_status = tk.Label(
            row2, text=req_label,
            font=("Segoe UI", 9), fg=SUCCESS if pkgs_ok else DANGER,
            bg=BG_PANEL, anchor="w"
        )
        self._req_status.pack(side="left", fill="x", expand=True)

        self._req_btn = tk.Button(
            row2, text="Install Packages",
            font=("Segoe UI", 9, "bold"), fg=FG_TEXT, bg=BTN_SETUP,
            activebackground=BTN_SETUP_HVR, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=12,
            command=self._install_requirements
        )
        self._req_btn.pack(side="right")
        if pkgs_ok:
            self._req_btn.config(state="disabled", text="Installed ✔")

        # --- ChromeDriver row ---
        cd_ok, cd_path = check_chromedriver()
        row3 = tk.Frame(self._setup_body, bg=BG_PANEL)
        row3.pack(fill="x", padx=12, pady=(4, 10))

        self._cd_status = tk.Label(
            row3,
            text=f"✅ ChromeDriver found" if cd_ok else "❌ ChromeDriver not found",
            font=("Segoe UI", 9), fg=SUCCESS if cd_ok else DANGER,
            bg=BG_PANEL, anchor="w"
        )
        self._cd_status.pack(side="left", fill="x", expand=True)

        self._cd_btn = tk.Button(
            row3, text="Setup ChromeDriver",
            font=("Segoe UI", 9, "bold"), fg=FG_TEXT, bg=BTN_SETUP,
            activebackground=BTN_SETUP_HVR, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=12,
            command=self._install_chromedriver
        )
        self._cd_btn.pack(side="right")
        if cd_ok:
            self._cd_btn.config(state="disabled", text="Installed ✔")

    def _toggle_setup(self):
        """Show/hide the setup tools body."""
        if self._setup_open.get():
            self._setup_body.pack_forget()
            self._setup_open.set(False)
            self._setup_toggle_btn.config(text="🔧  Setup Tools  ▼")
        else:
            self._setup_body.pack(fill="x")
            self._setup_open.set(True)
            self._setup_toggle_btn.config(text="🔧  Setup Tools  ▲")

    # ── Install handlers (run in background threads) ────────────────────
    def _install_python(self):
        self._py_btn.config(state="disabled", text="Downloading...")
        self._log("⬇  Downloading Python 3.11 installer...")
        threading.Thread(target=self._do_install_python, daemon=True).start()

    def _do_install_python(self):
        try:
            url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
            dest = os.path.join(os.environ.get("TEMP", "."), "python_installer.exe")
            self._log(f"   Saving to {dest}")
            # Download using Python's built-in urllib (no powershell needed)
            import urllib.request
            urllib.request.urlretrieve(url, dest)
            self._log("✅ Download complete. Launching installer...")
            self._log("   ⚠ IMPORTANT: Check 'Add Python to PATH' in the installer!")
            subprocess.Popen([dest, "InstallAllUsers=0", "PrependPath=1",
                              "Include_test=0"])
            self.after(0, lambda: self._py_btn.config(text="Installer open"))
        except Exception as e:
            self._log(f"❌ Python install failed: {e}")
            self.after(0, lambda: self._py_btn.config(
                state="normal", text="Retry Install"))

    def _install_requirements(self):
        self._req_btn.config(state="disabled", text="Installing...")
        self._log("📦 Installing pip packages...")
        threading.Thread(target=self._do_install_requirements, daemon=True).start()

    def _do_install_requirements(self):
        try:
            req_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().splitlines()[-5:]:
                self._log(f"   {line}")
            if result.returncode == 0:
                self._log("✅ All packages installed successfully.")
                self.after(0, lambda: [
                    self._req_btn.config(state="disabled", text="Installed ✔"),
                    self._req_status.config(text="✅ All packages installed",
                                            fg=SUCCESS)
                ])
            else:
                self._log(f"⚠ pip returned errors:\n{result.stderr[-300:]}")
                self.after(0, lambda: self._req_btn.config(
                    state="normal", text="Retry"))
        except Exception as e:
            self._log(f"❌ Package install failed: {e}")
            self.after(0, lambda: self._req_btn.config(
                state="normal", text="Retry"))

    def _install_chromedriver(self):
        self._cd_btn.config(state="disabled", text="Setting up...")
        self._log("🌐 Setting up ChromeDriver (auto-matching Chrome version)...")
        threading.Thread(target=self._do_install_chromedriver, daemon=True).start()

    def _do_install_chromedriver(self):
        try:
            # Ensure webdriver-manager is available
            try:
                from webdriver_manager.chrome import ChromeDriverManager
            except ImportError:
                self._log("   Installing webdriver-manager first...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "webdriver-manager"],
                    capture_output=True, check=True
                )
                from webdriver_manager.chrome import ChromeDriverManager

            # Detect Chrome version from filesystem
            from bot_engine import ViewerBot
            chrome_ver = ViewerBot._detect_chrome_version()
            if chrome_ver:
                self._log(f"   Detected Chrome {chrome_ver}")
                raw_path = ChromeDriverManager(driver_version=chrome_ver).install()
            else:
                raw_path = ChromeDriverManager().install()

            # Find actual chromedriver.exe (webdriver-manager may return wrong file)
            path = raw_path
            if not raw_path.endswith("chromedriver.exe"):
                search_dir = os.path.dirname(raw_path)
                for root, dirs, files in os.walk(search_dir):
                    for f in files:
                        if f == "chromedriver.exe":
                            path = os.path.join(root, f)
                            break

            self._log(f"✅ ChromeDriver ready at:\n   {path}")
            self.after(0, lambda: [
                self._cd_btn.config(state="disabled", text="Installed ✔"),
                self._cd_status.config(text="✅ ChromeDriver found", fg=SUCCESS)
            ])
        except Exception as e:
            self._log(f"❌ ChromeDriver setup failed: {e}")
            self.after(0, lambda: self._cd_btn.config(
                state="normal", text="Retry"))

    # ── Helpers ─────────────────────────────────────────────────────────
    def _add_placeholder(self, entry, text):
        entry._ph = text
        entry.insert(0, text)
        entry.config(fg=FG_DIM)
        entry.bind("<FocusIn>", lambda e: self._clear_ph(entry))
        entry.bind("<FocusOut>", lambda e: self._restore_ph(entry))

    def _clear_ph(self, entry):
        if entry.get() == entry._ph:
            entry.delete(0, "end")
            entry.config(fg=FG_TEXT)

    def _restore_ph(self, entry):
        if not entry.get():
            entry.insert(0, entry._ph)
            entry.config(fg=FG_DIM)

    def _on_slider(self, val):
        self.viewer_label.config(text=str(int(float(val))))

    def _log(self, msg):
        """Thread-safe log append."""
        def _append():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _append)

    # ── Proxy management card ────────────────────────────────────────────
    def _build_proxy_card(self):
        """Build the proxy paste/load panel."""
        card = tk.Frame(self, bg=BG_PANEL, bd=0,
                        highlightthickness=1,
                        highlightbackground="#3d2d6b")
        card.pack(fill="x", padx=28, pady=(6, 8))

        # Header row
        hdr = tk.Frame(card, bg=BG_PANEL)
        hdr.pack(fill="x", padx=16, pady=(10, 2))

        tk.Label(
            hdr, text="PROXIES (optional)",
            font=("Segoe UI", 9, "bold"),
            fg=FG_DIM, bg=BG_PANEL, anchor="w"
        ).pack(side="left")

        self.proxy_count_lbl = tk.Label(
            hdr, text="0 proxies",
            font=("Segoe UI", 9),
            fg=ACCENT, bg=BG_PANEL, anchor="e"
        )
        self.proxy_count_lbl.pack(side="right")

        # Proxy URL Row
        url_frame = tk.Frame(card, bg=BG_PANEL)
        url_frame.pack(fill="x", padx=16, pady=(4, 6))
        
        tk.Label(
            url_frame, text="Proxy URL:",
            font=("Segoe UI", 8),
            fg=FG_DIM, bg=BG_PANEL
        ).pack(side="left")
        
        self.proxy_url_entry = tk.Entry(
            url_frame, font=("Segoe UI", 9),
            bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#3d2d6b",
            highlightcolor=ACCENT
        )
        self.proxy_url_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=2)
        # Default pre-filled URL (Removing internal spaces if any were present)
        self.proxy_url_entry.insert(0, "https://proxy.webshare.io/api/v2/proxy/list/download/geeshigwdghvjmswvafrobowkuygfmwcqtldxafu/-/any/username/direct/-/?plan_id=12870208")
        
        fetch_url_btn = tk.Button(
            url_frame, text="Fetch",
            font=("Segoe UI", 8, "bold"),
            bg=ACCENT, fg="white",
            activebackground=BTN_SETUP_HVR,
            activeforeground="white",
            relief="flat", cursor="hand2", bd=0,
            padx=8,
            command=self._fetch_proxies_now
        )
        fetch_url_btn.pack(side="right")

        # Text area for pasting proxies
        self.proxy_text = tk.Text(
            card, height=5, font=("Consolas", 9),
            bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#3d2d6b",
            highlightcolor=ACCENT, wrap="word"
        )
        self.proxy_text.pack(
            fill="x", padx=16, pady=(4, 6)
        )
        self.proxy_text.insert(
            "1.0",
            "# Paste proxies here (one per line)\n"
            "# Format: http://ip:port or user:pass:ip:port\n"
        )
        self.proxy_text.bind(
            "<KeyRelease>", lambda e: self._update_proxy_count()
        )

        # Button row
        btn_row = tk.Frame(card, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=16, pady=(0, 10))

        load_btn = tk.Button(
            btn_row, text="\U0001f4c2  Load .txt",
            font=("Segoe UI", 9),
            bg=BTN_SETUP, fg=FG_TEXT,
            activebackground=BTN_SETUP_HVR,
            activeforeground="white",
            relief="flat", cursor="hand2", bd=0,
            command=self._load_proxy_file
        )
        load_btn.pack(side="left", padx=(0, 6))

        save_btn = tk.Button(
            btn_row, text="\U0001f4be  Save Proxies",
            font=("Segoe UI", 9),
            bg=BTN_SETUP, fg=FG_TEXT,
            activebackground=BTN_SETUP_HVR,
            activeforeground="white",
            relief="flat", cursor="hand2", bd=0,
            command=self._save_proxies
        )
        save_btn.pack(side="left", padx=(0, 6))

        clear_btn = tk.Button(
            btn_row, text="Clear",
            font=("Segoe UI", 9),
            bg="#3d1a1a", fg="#e0a0a0",
            activebackground=DANGER,
            activeforeground="white",
            relief="flat", cursor="hand2", bd=0,
            command=self._clear_proxies
        )
        clear_btn.pack(side="right")

        # Load existing proxies.txt if present
        self._load_existing_proxies()

    def _load_existing_proxies(self):
        """Pre-fill text area from proxies.txt if it exists."""
        proxy_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "proxies.txt"
        )
        if os.path.isfile(proxy_path):
            with open(proxy_path, "r") as f:
                content = f.read().strip()
            if content:
                self.proxy_text.delete("1.0", "end")
                self.proxy_text.insert("1.0", content)
        self._update_proxy_count()

    def _load_proxy_file(self):
        """Open file dialog to load a .txt proxy list."""
        path = filedialog.askopenfilename(
            title="Select Proxy List",
            filetypes=[
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return
        try:
            with open(path, "r") as f:
                content = f.read().strip()
            self.proxy_text.delete("1.0", "end")
            self.proxy_text.insert("1.0", content)
            self._update_proxy_count()
            self._log(f"Loaded proxies from: {path}")
        except Exception as e:
            messagebox.showerror(
                "Load Error", f"Could not read file:\n{e}"
            )

    def _save_proxies(self):
        """Save text area content to proxies.txt."""
        content = self.proxy_text.get("1.0", "end").strip()
        proxy_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "proxies.txt"
        )
        try:
            with open(proxy_path, "w") as f:
                f.write(content + "\n")
            count = self._count_proxies(content)
            self._log(
                f"Saved {count} proxies to proxies.txt"
            )
        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Could not write proxies.txt:\n{e}"
            )

    def _clear_proxies(self):
        """Clear the proxy text area."""
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert(
            "1.0",
            "# Paste proxies here (one per line)\n"
            "# Format: http://ip:port or "
            "socks5://ip:port\n"
        )
        self._update_proxy_count()

    def _count_proxies(self, text):
        """Count non-comment, non-empty lines."""
        count = 0
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                count += 1
        return count

    def _update_proxy_count(self):
        """Update the proxy count label."""
        content = self.proxy_text.get("1.0", "end")
        count = self._count_proxies(content)
        if count > 0:
            self.proxy_count_lbl.config(
                text=f"{count} proxies", fg=SUCCESS
            )
        else:
            self.proxy_count_lbl.config(
                text="no proxies (direct mode)",
                fg=FG_DIM
            )

    def _fetch_proxies_now(self):
        """Manually trigger proxy fetch from URL."""
        url = self.proxy_url_entry.get().strip()
        if not url:
            messagebox.showinfo("Wait", "Please enter a Proxy URL first.")
            return
            
        self.proxy_count_lbl.config(text="Fetching...", fg=ACCENT)
        self.update_idletasks()
        
        plist = fetch_proxies_from_url(url)
        if not plist:
            self.proxy_count_lbl.config(text="Fetch failed", fg=DANGER)
            messagebox.showerror("Error", "Failed to fetch proxies from URL.")
            self._update_proxy_count() # revert label
            return
            
        # Add to text area
        self.proxy_text.delete("1.0", "end")
        self.proxy_text.insert("1.0", "# Fetched from URL\n")
        for p in plist:
            self.proxy_text.insert("end", f"{p}\n")
            
        self._update_proxy_count()
        messagebox.showinfo("Success", f"Loaded {len(plist)} proxies from URL.")

    # ── Bot lifecycle ───────────────────────────────────────────────────
    def _on_launch(self):
        channel = self.channel_entry.get().strip()
        if not channel or channel == getattr(
            self.channel_entry, '_ph', ''
        ):
            messagebox.showwarning(
                "Missing info",
                "Please enter your Twitch channel name."
            )
            return

        # Auto-save proxies before launch
        self._save_proxies()

        # Get proxy selection & rotation setting
        proxy_idx = self.proxy_combo.current() + 1
        rotate = self.rotate_var.get()
        viewer_count = self.viewer_var.get()

        self.launch_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("Running...")

        proxy_name = PROXY_SERVERS.get(
            proxy_idx, PROXY_SERVERS[1]
        )[0]
        self._log(f"--- Session started ---")
        self._log(f"Channel:  {channel}")
        self._log(f"Viewers:  {viewer_count}")
        self._log(
            f"Proxy:    {proxy_name} "
            f"({'rotate' if rotate else 'fixed'})"
        )

        self.bot = ViewerBot(
            proxy_id=proxy_idx,
            channel_name=channel,
            viewer_count=viewer_count,
            on_status=self._log,
            on_finish=self._on_bot_finished,
            rotate_proxies=rotate,
            proxy_url=self.proxy_url_entry.get().strip()
        )
        self.bot.start()

    def _on_stop(self):
        if self.bot:
            self.status_var.set("Stopping...")
            self.stop_btn.config(state="disabled")
            self.bot.stop()

    def _on_bot_finished(self):
        def _finish_ui():
            self.bot = None
            self.launch_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.status_var.set("Stopped")
            self._log("─── Session ended ───")
        self.after(0, _finish_ui)

    def on_closing(self):
        if self.bot:
            self.bot.stop()
        self.destroy()


if __name__ == "__main__":
    app = TwitchBotGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
