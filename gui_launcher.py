"""
Twitch Viewer Bot — GUI Launcher
A user-friendly graphical interface for non-technical users.
No extra dependencies beyond Python's built-in tkinter.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import subprocess
import shutil
import sys
import os
import ctypes
import struct

# ── Ensure project root is on path ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_engine import PROXY_SERVERS, ViewerBot  # noqa: E402

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
MB_PER_TAB = 75  # approx headless Chrome tab memory
RAM_USAGE_RATIO = 0.70  # use at most 70% of *available* RAM


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
        return 30  # safe fallback
    usable = int(avail_mb * RAM_USAGE_RATIO)
    suggested = max(5, usable // MB_PER_TAB)
    return min(suggested, 300)  # hard cap


def max_viewers(avail_mb):
    """Absolute max viewers before likely OOM."""
    if avail_mb is None:
        return 200
    return max(10, int(avail_mb * 0.90) // MB_PER_TAB)


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
        self.geometry("560x920")
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
        self.proxy_combo.pack(fill="x", padx=16, pady=(0, 10))

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
        tk.Label(card, text="💡 Tip: set ~50% more than desired (e.g. 30 to get ~20)",
                 font=("Segoe UI", 8), fg=FG_DIM, bg=BG_PANEL,
                 anchor="w").pack(fill="x", padx=16, pady=(0, 12))

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
            # Download with PowerShell (built-in on Windows)
            subprocess.run(
                ["powershell", "-Command",
                 f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}'"],
                check=True, capture_output=True
            )
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

            path = ChromeDriverManager().install()
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

    # ── Bot lifecycle ───────────────────────────────────────────────────
    def _on_launch(self):
        channel = self.channel_entry.get().strip()
        if not channel or channel == getattr(self.channel_entry, '_ph', ''):
            messagebox.showwarning("Missing info", "Please enter your Twitch channel name.")
            return

        proxy_idx = self.proxy_combo.current() + 1   # 1-based
        viewer_count = self.viewer_var.get()

        self.launch_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("Running...")

        self._log(f"─── Session started ───")
        self._log(f"Channel:  {channel}")
        self._log(f"Viewers:  {viewer_count}")
        self._log(f"Proxy:    {proxy_idx}")

        self.bot = ViewerBot(
            proxy_id=proxy_idx,
            channel_name=channel,
            viewer_count=viewer_count,
            on_status=self._log
        )
        self.bot.start()

    def _on_stop(self):
        if self.bot:
            self.bot.stop()
            self.bot = None
        self.launch_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("Stopped")
        self._log("─── Session ended ───\n")

    def on_closing(self):
        if self.bot:
            self.bot.stop()
        self.destroy()


if __name__ == "__main__":
    app = TwitchBotGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
