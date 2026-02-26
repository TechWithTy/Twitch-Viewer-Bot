"""
Twitch Viewer Bot Engine
Extracted core logic so the GUI launcher can drive it.
"""

import time
import warnings
import threading
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Proxy server registry
PROXY_SERVERS = {
    1: ("blockaway.net", "https://www.blockaway.net"),
    2: ("croxyproxy.com", "https://www.croxyproxy.com"),
    3: ("croxyproxy.rocks", "https://www.croxyproxy.rocks"),
    4: ("croxy.network", "https://www.croxy.network"),
    5: ("croxy.org", "https://www.croxy.org"),
    6: ("youtubeunblocked.live", "https://www.youtubeunblocked.live"),
    7: ("croxyproxy.net", "https://www.croxyproxy.net"),
}


class ViewerBot:
    """Manages the Selenium-based viewer bot lifecycle."""

    def __init__(self, proxy_id, channel_name, viewer_count, on_status=None):
        self.proxy_id = proxy_id
        self.channel_name = channel_name.strip()
        self.viewer_count = viewer_count
        self.on_status = on_status or (lambda msg: None)
        self.driver = None
        self._stop_event = threading.Event()

    def _report(self, msg):
        self.on_status(msg)

    def _build_driver(self):
        """Build a headless Chrome driver, auto-downloading chromedriver."""
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except Exception:
            # Fallback: use local chromedriver.exe
            service = Service("chromedriver.exe")

        opts = webdriver.ChromeOptions()
        opts.add_experimental_option('excludeSwitches', ['enable-logging'])
        opts.add_argument('--disable-logging')
        opts.add_argument('--log-level=3')
        opts.add_argument('--headless')
        opts.add_argument('--mute-audio')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--no-sandbox')

        import os
        ext = os.path.join(os.path.dirname(__file__), 'adblock.crx')
        if os.path.exists(ext):
            opts.add_extension(ext)

        return webdriver.Chrome(service=service, options=opts)

    def start(self):
        """Launch viewers in a background thread."""
        self._stop_event.clear()
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        proxy_name, proxy_url = PROXY_SERVERS.get(
            self.proxy_id, PROXY_SERVERS[1]
        )
        self._report(f"Using proxy: {proxy_name}")
        self._report("Starting Chrome (headless)...")

        try:
            self.driver = self._build_driver()
        except Exception as e:
            self._report(f"ERROR: Could not start Chrome.\n{e}")
            return

        try:
            self.driver.get("https://www.google.com/?zx=1&no_sw_cr=1")
            time.sleep(2)
        except Exception:
            pass

        self._report(f"Opening {self.viewer_count} viewer tabs...")

        self.driver.get(proxy_url)

        for i in range(self.viewer_count):
            if self._stop_event.is_set():
                self._report("Stopped by user.")
                break

            self._report(f"Launching viewer {i + 1}/{self.viewer_count}...")
            self.driver.execute_script(f"window.open('{proxy_url}')")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.driver.get(proxy_url)
            time.sleep(1)

            try:
                text_box = self.driver.find_element(By.ID, 'url')
                text_box.send_keys(f'www.twitch.tv/{self.channel_name}')
                text_box.send_keys(Keys.RETURN)
            except Exception:
                self._report(f"  Tab {i + 1}: proxy input not found, skipping.")

        if not self._stop_event.is_set():
            self._report("All viewers sent! Keep this running to maintain views.")

    def stop(self):
        """Signal the bot to stop and close the browser."""
        self._stop_event.set()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._report("Bot stopped.")
