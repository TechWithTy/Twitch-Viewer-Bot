import os
import time
import warnings
import requests
from pystyle import Center, Colors, Colorate

from bot_engine import PROXY_SERVERS, ViewerBot

warnings.filterwarnings("ignore", category=DeprecationWarning)


def check_for_updates():
    try:
        resp = requests.get(
            "https://raw.githubusercontent.com/"
            "Kichi779/Twitch-Viewer-Bot/main/version.txt",
            timeout=8,
        )
        remote_version = resp.text.strip()
        with open("version.txt", "r") as f:
            local_version = f.read().strip()
        if remote_version != local_version:
            print(
                "A new version is available. Please download "
                "the latest version from GitHub."
            )
            time.sleep(2)
            return False
        return True
    except Exception:
        return True


def print_announcement():
    try:
        resp = requests.get(
            "https://raw.githubusercontent.com/"
            "Kichi779/Twitch-Viewer-Bot/main/announcement.txt",
            headers={"Cache-Control": "no-cache"},
            timeout=8,
        )
        return resp.text.strip()
    except Exception:
        return "Could not retrieve announcement from GitHub."


def print_banner():
    os.system("title Kichi779 - Twitch Viewer Bot @kichi#0779 ")
    print(
        Colorate.Vertical(
            Colors.green_to_cyan,
            Center.XCenter(
                """
                        ▄█   ▄█▄  ▄█    ▄████████    ▄█    █▄     ▄█
                        ███ ▄███▀ ███    ███    ███    ███    ███    ███
                        ███▐██▀   ███▌   ███    █▀     ███    ███    ███▌
                       ▄█████▀    ███▌   ███          ▄███▄▄▄▄███▄▄ ███▌
                      ▀▀█████▄    ███▌   ███         ▀▀███▀▀▀▀███▀  ███▌
                        ███▐██▄   ███    ███    █▄     ███    ███    ███
                        ███ ▀███▄ ███    ███    ███    ███    ███    ███
                        ███   ▀█▀ █▀     ████████▀     ███    █▀    █▀
                        ▀
 Improvements can be made to the code. If you're getting an error, visit my discord.
                              Discord discord.gg/u4T67NU6xb
                              Github  github.com/kichi779
                """
            ),
        )
    )


def parse_int(prompt, low, high):
    while True:
        raw = input(prompt).strip()
        try:
            val = int(raw)
            if low <= val <= high:
                return val
        except ValueError:
            pass
        print(f"Enter a number between {low} and {high}.")


def main():
    if not check_for_updates():
        return

    announcement = print_announcement()
    print_banner()
    print("")
    print(Colors.red, Center.XCenter("ANNOUNCEMENT"))
    print(Colors.yellow, Center.XCenter(announcement))
    print("")

    print(Colors.green, "Proxy Server 1 Is Recommended")
    print(Colorate.Vertical(Colors.green_to_blue, "Please select a proxy server (1..7):"))
    for i in range(1, 8):
        name = PROXY_SERVERS[i][0]
        print(Colorate.Vertical(Colors.red_to_blue, f"Proxy Server {i} ({name})"))
    proxy_choice = parse_int("> ", 1, 7)

    twitch_username = input(
        Colorate.Vertical(
            Colors.green_to_blue,
            "Enter your channel name (e.g Kichi779): ",
        )
    ).strip()
    while not twitch_username:
        twitch_username = input("Channel name cannot be empty: ").strip()

    viewer_count = parse_int(
        Colorate.Vertical(
            Colors.cyan_to_blue,
            "How many viewers do you want to send? ",
        ),
        1,
        200,
    )
    rotate = input("Auto-rotate healthy proxies? (Y/n): ").strip().lower() != "n"
    proxy_url = input("Enter Proxy URL (optional, e.g. Webshare): ").strip()

    os.system("cls")
    print_banner()
    print("")
    print(
        Colors.red,
        Center.XCenter(
            "Viewers are launching. Keep this window open to maintain views."
        ),
    )

    bot = ViewerBot(
        proxy_id=proxy_choice,
        channel_name=twitch_username,
        viewer_count=viewer_count,
        on_status=print,
        rotate_proxies=rotate,
        proxy_url=proxy_url
    )
    bot.start()

    try:
        input(
            Colorate.Vertical(
                Colors.red_to_blue,
                "Press ENTER to stop all viewers and close the program.",
            )
        )
    finally:
        bot.stop()


if __name__ == "__main__":
    main()
