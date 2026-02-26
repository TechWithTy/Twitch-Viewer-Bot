"""
Twitch Viewer Bot Engine
Launches headless Chrome instances that watch a Twitch stream.
Supports web proxy sites (CroxyProxy, BlockAway, etc.)
with health checking and automatic rotation.
Optionally supports HTTP/SOCKS proxies via proxies.txt.
"""

import os
import time
import shutil
import random
import zipfile
import warnings
import requests
import threading
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Web proxy registry
WEB_PROXIES = {
    1: ("blockaway.net", "https://www.blockaway.net"),
    2: ("croxyproxy.com", "https://www.croxyproxy.com"),
    3: ("croxyproxy.rocks", "https://www.croxyproxy.rocks"),
    4: ("croxy.network", "https://www.croxy.network"),
    5: ("croxy.org", "https://www.croxy.org"),
    6: ("youtubeunblocked.live",
        "https://www.youtubeunblocked.live"),
    7: ("croxyproxy.net", "https://www.croxyproxy.net"),
}

PROXY_SERVERS = WEB_PROXIES  # GUI compat

_USER_AGENTS = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/145.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/144.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/145.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (X11; Linux x86_64) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/145.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/143.0.0.0 Safari/537.36"),
]

_PROXY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "proxies.txt"
)


def load_proxy_list(path=None):
    """Load proxy list from file."""
    path = path or _PROXY_FILE
    if not os.path.isfile(path):
        return []
    proxies = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Handle user:pass:ip:port or ip:port:user:pass or just ip:port
            parts = line.split(":")
            if len(parts) == 4:
                # Common format: ip:port:user:pass
                proxies.append(line)
            else:
                if "://" not in line:
                    line = f"http://{line}"
                proxies.append(line)
    return proxies


def fetch_proxies_from_url(url):
    """Fetch proxy list from a URL (e.g. Webshare)."""
    if not url:
        return []
    # Remove all whitespace (including internal spaces/tabs if copy-pasted poorly)
    url = "".join(url.split())
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        content = response.text
        proxies = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            proxies.append(line)
        return proxies
    except Exception as e:
        print(f"Failed to fetch proxies from URL: {e}")
        return []


def create_proxy_auth_extension(proxy_host, proxy_port,
                                proxy_user, proxy_pass,
                                scheme='http', plugin_path=None):
    """
    Create a Chrome extension to handle proxy authentication.
    Chrome doesn't support 'user:pass@ip:port' in --proxy-server.
    """
    if plugin_path is None:
        plugin_path = os.path.join(
            os.environ.get('TEMP', os.getcwd()),
            f'proxy_auth_plugin_{proxy_host}_{proxy_port}.zip'
        )

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "%s",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["foobar.com"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
            callbackFn,
            {urls: ["<all_urls>"]},
            ['blocking']
    );
    """ % (scheme, proxy_host, proxy_port, proxy_user, proxy_pass)

    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return plugin_path


class ViewerBot:
    """Manages headless Chrome viewer instances."""

    def __init__(self, proxy_id, channel_name, viewer_count,
                 on_status=None, on_finish=None,
                 rotate_proxies=False, proxy_url=None):
        self.proxy_id = proxy_id
        self.channel_name = channel_name.strip()
        self.viewer_count = viewer_count
        self.on_status = on_status or (lambda msg: None)
        self.on_finish = on_finish or (lambda: None)
        self.rotate_proxies = rotate_proxies
        self.proxy_url = proxy_url
        self.drivers = []
        self._temp_files = []
        self._stop_event = threading.Event()

    def _report(self, msg):
        self.on_status(msg)

    # -- Chrome detection --
    @staticmethod
    def _detect_chrome_version():
        chrome_dirs = [
            r"C:\Program Files\Google\Chrome\Application",
            r"C:\Program Files (x86)\Google\Chrome"
            r"\Application",
            os.path.expandvars(
                r"%LOCALAPPDATA%\Google\Chrome\Application"
            ),
        ]
        for base in chrome_dirs:
            if not os.path.isdir(base):
                continue
            for entry in sorted(
                os.listdir(base), reverse=True
            ):
                full = os.path.join(base, entry)
                if entry[0].isdigit() and os.path.isdir(full):
                    return entry
        return None

    @staticmethod
    def _resolve_driver_path(raw_path):
        if raw_path.endswith("chromedriver.exe"):
            return raw_path
        for root, _, files in os.walk(
            os.path.dirname(raw_path)
        ):
            if "chromedriver.exe" in files:
                return os.path.join(root, "chromedriver.exe")
        parent = os.path.dirname(os.path.dirname(raw_path))
        for root, _, files in os.walk(parent):
            if "chromedriver.exe" in files:
                return os.path.join(root, "chromedriver.exe")
        return raw_path

    def _get_chromedriver_path(self):
        from webdriver_manager.chrome import ChromeDriverManager
        ver = self._detect_chrome_version()
        if ver:
            self._report(f"Detected Chrome {ver}")
            mgr = ChromeDriverManager(driver_version=ver)
        else:
            self._report("Chrome version unknown, latest")
            mgr = ChromeDriverManager()
        self._report("Downloading/verifying ChromeDriver...")
        raw = mgr.install()
        path = self._resolve_driver_path(raw)
        self._report(f"ChromeDriver ready: {path}")
        return path

    # -- Driver builder --
    def _build_driver(self, driver_path, proxy=None,
                      instance_id=0):
        service = Service(driver_path)
        opts = webdriver.ChromeOptions()
        # Stealth: Remove automation flags and exclude logging
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        opts.add_experimental_option("useAutomationExtension", False)
        
        opts.add_argument("--disable-logging")
        opts.add_argument("--log-level=3")
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1280,720")
        opts.add_argument(
            "--autoplay-policy=no-user-gesture-required"
        )
        ua = _USER_AGENTS[instance_id % len(_USER_AGENTS)]
        opts.add_argument(f"--user-agent={ua}")
        opts.add_argument("--mute-audio")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        # Headless=new supports extensions, so we don't disable them if we need them
        # opts.add_argument("--disable-extensions") 
        opts.add_argument("--disable-background-networking")
        opts.add_argument("--disable-default-apps")
        opts.add_argument("--disable-sync")
        opts.add_argument("--disable-translate")
        opts.add_argument("--no-first-run")

        if proxy:
            # Handle user:pass:ip:port format
            parts = proxy.split(":")
            if len(parts) == 4:
                # Common format: ip:port:user:pass
                ip, port, user, pw = parts
                plugin_path = create_proxy_auth_extension(
                    ip, port, user, pw
                )
                opts.add_extension(plugin_path)
                self._temp_files.append(plugin_path)
            else:
                opts.add_argument(f"--proxy-server={proxy}")
            
            opts.add_argument("--ignore-certificate-errors")

        # Load AdBlock if available
        ext_path = os.path.join(os.getcwd(), 'adblock.crx')
        if os.path.exists(ext_path):
            opts.add_extension(ext_path)

        return webdriver.Chrome(service=service, options=opts)

    # -- Stream activation --
    def _activate_stream(self, driver):
        """Dismiss popups, start video, verify playback."""
        try:
            driver.execute_script("""
                var btns = document.querySelectorAll(
                    'button, [role="button"], a'
                );
                for (var b of btns) {
                    var t = (b.textContent||'')
                        .trim().toLowerCase();
                    if (t==='proceed' || t==='accept'
                        || t==='start watching') {
                        b.click(); break;
                    }
                }
            """)
            time.sleep(1)
        except Exception:
            pass

        try:
            driver.execute_script("""
                var v = document.querySelector('video');
                if (v) {
                    v.muted = true;
                    v.play().catch(function(){});
                }
            """)
            time.sleep(3)
        except Exception:
            pass

        try:
            t1 = driver.execute_script(
                "var v=document.querySelector('video');"
                "return v ? v.currentTime : -1;"
            )
            time.sleep(2)
            t2 = driver.execute_script(
                "var v=document.querySelector('video');"
                "return v ? v.currentTime : -1;"
            )
            if t2 is not None and t1 is not None:
                if t2 > t1 and t2 > 0:
                    return True
                if t2 > 0:
                    driver.execute_script(
                        "var v=document.querySelector('video');"
                        "if(v){v.muted=true;"
                        "v.play().catch(()=>{});}"
                    )
                    time.sleep(3)
                    t3 = driver.execute_script(
                        "var v=document.querySelector('video');"
                        "return v ? v.currentTime : -1;"
                    )
                    return t3 is not None and t3 > t2
        except Exception:
            pass
        return False

    # -- Web proxy health check --
    def _check_web_proxy(self, driver_path, web_url):
        """Test if a web proxy site loads. Returns True/False."""
        d = None
        try:
            d = self._build_driver(driver_path)
            d.set_page_load_timeout(12)
            d.get(web_url)
            time.sleep(2)
            # Check if there's a URL input box
            has_input = d.execute_script("""
                var inp = document.querySelector(
                    'input[name="url"], input[id="url"], '
                    + 'input[type="url"], input[type="text"]'
                );
                return !!inp;
            """)
            d.quit()
            return bool(has_input)
        except Exception:
            if d:
                try:
                    d.quit()
                except Exception:
                    pass
            return False

    # -- Launch via web proxy --
    def _launch_web_proxy(self, driver, web_url, viewer_num):
        """Load Twitch through a web proxy site."""
        try:
            driver.get(web_url)
            time.sleep(5)
        except Exception as e:
            err = str(e).split('\n')[0][:50]
            self._report(
                f"  Viewer {viewer_num}: "
                f"proxy page failed -- {err}"
            )
            return False

        # Find the URL input
        try:
            url_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    'input[name="url"], input[id="url"], '
                    'input[type="url"], input[type="text"]'
                ))
            )
        except Exception:
            self._report(
                f"  Viewer {viewer_num}: "
                "proxy site didn't load properly"
            )
            return False

        try:
            url_input.clear()
            url_input.send_keys(
                f"https://www.twitch.tv/{self.channel_name}"
            )
            time.sleep(0.3)
            # Try submit button
            try:
                btn = driver.find_element(
                    By.CSS_SELECTOR,
                    'button[type="submit"], '
                    '#requestSubmit, '
                    'input[type="submit"]'
                )
                btn.click()
            except Exception:
                url_input.send_keys(Keys.RETURN)

            self._report(
                f"  Viewer {viewer_num}: submitted, loading..."
            )
            time.sleep(12)

            playing = self._activate_stream(driver)
            if playing:
                self._report(
                    f"  Viewer {viewer_num}: "
                    ">> stream PLAYING"
                )
            else:
                self._report(
                    f"  Viewer {viewer_num}: "
                    "-- loaded (video may be buffering)"
                )
            return True
        except Exception as e:
            err = str(e).split('\n')[0][:50]
            self._report(
                f"  Viewer {viewer_num}: failed -- {err}"
            )
            return False

    # -- Launch direct (with SOCKS/HTTP proxy) --
    def _launch_direct(self, driver, viewer_num):
        """Navigate directly to Twitch (proxy at Chrome level)."""
        url = f"https://www.twitch.tv/{self.channel_name}"
        try:
            driver.get(url)
            time.sleep(8)
            playing = self._activate_stream(driver)
            if playing:
                self._report(
                    f"  Viewer {viewer_num}: "
                    ">> stream PLAYING"
                )
            else:
                ct = 0
                try:
                    ct = driver.execute_script(
                        "var v=document.querySelector('video');"
                        "return v ? v.currentTime : 0;"
                    ) or 0
                except Exception:
                    pass
                if ct > 0:
                    self._report(
                        f"  Viewer {viewer_num}: "
                        f">> playing (t={ct:.1f}s)"
                    )
                else:
                    self._report(
                        f"  Viewer {viewer_num}: "
                        "-- loaded, video may be stalled"
                    )
            return True
        except Exception as e:
            err = str(e).split('\n')[0][:60]
            self._report(
                f"  Viewer {viewer_num}: FAIL -- {err}"
            )
            return False

    def _find_working_proxies(self, driver_path, start_id):
        """Test all web proxies once and return healthy proxies in start order."""
        ids = list(WEB_PROXIES.keys())
        if start_id in ids:
            idx = ids.index(start_id)
            ids = ids[idx:] + ids[:idx]

        healthy = []
        for pid in ids:
            if self._stop_event.is_set():
                break
            name, url = WEB_PROXIES[pid]
            self._report(f"Testing proxy {pid} ({name})...")
            if self._check_web_proxy(driver_path, url):
                self._report(f"  >> {name} is working!")
                healthy.append((pid, name, url))
            else:
                self._report(f"  -- {name} is down")
        return healthy

    # -- Public API --
    def start(self):
        self._stop_event.clear()
        thread = threading.Thread(target=self._run_safe,
                                  daemon=True)
        thread.start()

    def _run_safe(self):
        try:
            self._run()
        finally:
            try:
                self.on_finish()
            except Exception:
                pass

    def _run(self):
        try:
            driver_path = self._get_chromedriver_path()
        except Exception as e:
            self._report(f"ERROR: ChromeDriver failed.\n{e}")
            return

        # Check for proxy source: URL first, then local file
        ip_proxies = []
        if self.proxy_url:
            self._report(f"Fetching proxies from URL: {self.proxy_url}")
            ip_proxies = fetch_proxies_from_url(self.proxy_url)
            if ip_proxies:
                self._report(f"Successfully fetched {len(ip_proxies)} proxies!")
            else:
                self._report("Warning: Could not fetch from URL, checking proxies.txt")

        if not ip_proxies:
            ip_proxies = load_proxy_list()

        use_ip_proxies = len(ip_proxies) > 0

        if use_ip_proxies:
            self._report(
                f"Found {len(ip_proxies)} IP proxies"
            )
            self._report(
                "Each viewer gets a unique IP!"
            )
            web_proxy_plan = []
        else:
            # Use web proxy approach
            self._report(
                "Using web proxy mode..."
            )
            healthy = self._find_working_proxies(
                driver_path, self.proxy_id
            )
            if not healthy:
                self._report(
                    "ERROR: No working web proxies found!"
                )
                self._report(
                    "All 7 proxy sites are down. "
                    "Try again later or add IP proxies "
                    "to proxies.txt."
                )
                return
            selected = healthy[0]
            if not self.rotate_proxies:
                picked = None
                for item in healthy:
                    if item[0] == self.proxy_id:
                        picked = item
                        break
                selected = picked or healthy[0]
                web_proxy_plan = [selected]
                self._report(
                    f"\nUsing fixed proxy: {selected[1]} "
                    f"(proxy {selected[0]})"
                )
                if selected[0] != self.proxy_id:
                    self._report(
                        f"Selected proxy {self.proxy_id} was "
                        "down; switched to first healthy proxy."
                    )
            else:
                web_proxy_plan = healthy
                names = ", ".join(
                    f"{pid}:{name}" for pid, name, _ in healthy
                )
                self._report(
                    f"\nAuto-rotate enabled across "
                    f"{len(healthy)} healthy proxies: {names}"
                )

        self._report(
            f"\nLaunching {self.viewer_count} viewers for "
            f"twitch.tv/{self.channel_name}..."
        )

        for i in range(self.viewer_count):
            if self._stop_event.is_set():
                self._report("Stopped by user.")
                break

            viewer_num = i + 1
            self._report(
                f"Viewer {viewer_num}/{self.viewer_count}: "
                "starting..."
            )

            # Pick proxy
            ip_proxy = None
            if use_ip_proxies:
                ip_proxy = ip_proxies[
                    i % len(ip_proxies)
                ]
                self._report(f"  IP proxy: {ip_proxy}")
                web_url = None
                web_name = None
                web_pid = None
            else:
                web_pid, web_name, web_url = web_proxy_plan[
                    i % len(web_proxy_plan)
                ]
                self._report(
                    f"  Web proxy: {web_name} "
                    f"(proxy {web_pid})"
                )

            try:
                driver = self._build_driver(
                    driver_path, proxy=ip_proxy,
                    instance_id=i
                )
                driver.set_page_load_timeout(30)
                self.drivers.append(driver)
            except Exception as e:
                self._report(
                    f"  Viewer {viewer_num}: "
                    f"Chrome failed -- {e}"
                )
                continue

            if use_ip_proxies:
                self._launch_direct(driver, viewer_num)
            else:
                self._launch_web_proxy(
                    driver, web_url, viewer_num
                )

            time.sleep(random.uniform(2, 4))

        if not self._stop_event.is_set():
            active = len(self.drivers)
            self._report(
                f"\n-- {active} viewer(s) running --"
            )
            self._report(
                "Keep this window open to maintain views."
            )

    def stop(self):
        self._stop_event.set()
        for d in self.drivers:
            try:
                d.quit()
            except Exception:
                pass
        self.drivers.clear()
        self._report("Bot stopped -- all browsers closed.")

        # Cleanup temp proxy extension files
        for tmp in self._temp_files:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
        self._temp_files.clear()
