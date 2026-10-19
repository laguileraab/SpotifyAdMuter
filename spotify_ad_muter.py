"""Tray app that mutes Spotify (and only Spotify) while an ad is playing.

Detection: Spotify reports ads to the Windows media controls with no album.
As a fallback, while a track plays the Spotify window title is "Artist - Title",
and during ads it loses the " - " separator. Muting is done on Spotify's own
audio session in the Windows volume mixer, so other apps are unaffected.

The process idles in the background and the tray icon only appears while
Spotify is running.
"""

import asyncio
import sys
import threading
import winreg
from dataclasses import dataclass
from pathlib import Path

import comtypes
import psutil
import pystray
import win32api
import win32event
import win32gui
import win32process
import winerror
from PIL import Image, ImageDraw
from pycaw.pycaw import AudioUtilities
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

APP_NAME = "SpotifyAdMuter"
POLL_SECONDS = 0.5
IDLE_POLL_SECONDS = 2.0
PAUSED_TITLES = {"Spotify Free", "Spotify Premium"}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def spotify_pids() -> set[int]:
    return {
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name"])
        if (p.info["name"] or "").lower() == "spotify.exe"
    }


def spotify_title(pids: set[int]) -> str | None:
    titles: list[str] = []

    def collect(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        # The player window keeps its title even when hidden in the tray.
        if pid not in pids or not win32gui.GetClassName(hwnd).startswith("Chrome_WidgetWin"):
            return
        title = win32gui.GetWindowText(hwnd)
        if title:
            titles.append(title)

    win32gui.EnumWindows(collect, None)
    return titles[0] if titles else None


@dataclass
class MediaInfo:
    playing: bool
    artist: str
    album: str


class SpotifyMedia:
    """Reads Spotify's entry in the Windows media controls (the volume flyout)."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.manager = self.loop.run_until_complete(MediaManager.request_async())

    def read(self) -> MediaInfo | None:
        for session in self.manager.get_sessions():
            if "spotify" in session.source_app_user_model_id.lower():
                props = self.loop.run_until_complete(session.try_get_media_properties_async())
                status = session.get_playback_info().playback_status
                return MediaInfo(status == PlaybackStatus.PLAYING, props.artist or "", props.album_title or "")
        return None


def is_ad(title: str | None, media: MediaInfo | None) -> bool:
    # Ads are reported with no album; the advertiser (or nothing) is the artist.
    if media is not None:
        if not media.playing:
            return False
        if not media.artist or not media.album:
            return True
    return title is not None and title not in PAUSED_TITLES and " - " not in title


def set_spotify_mute(pids: set[int], mute: bool) -> None:
    for session in AudioUtilities.GetAllSessions():
        if session.Process and session.ProcessId in pids:
            session.SimpleAudioVolume.SetMute(1 if mute else 0, None)


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{Path(__file__).resolve()}"'


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_startup(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def make_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color)
    # Speaker glyph
    draw.polygon([(18, 26), (26, 26), (36, 16), (36, 48), (26, 38), (18, 38)], fill="white")
    draw.arc((34, 22, 48, 42), -60, 60, fill="white", width=3)
    return img


ICONS = {
    "on": make_icon("#1DB954"),
    "muting": make_icon("#E0393E"),
    "off": make_icon("#777777"),
}


class AdMuter:
    def __init__(self) -> None:
        self.enabled = True
        self.muted = True  # Clears a leftover mute from a previous crash on first poll.
        self.stop = threading.Event()
        self.media: SpotifyMedia | None = None
        self.icon = pystray.Icon(
            APP_NAME,
            ICONS["on"],
            "Spotify Ad Muter",
            menu=pystray.Menu(
                pystray.MenuItem("Enabled", self.toggle_enabled, checked=lambda _: self.enabled, default=True),
                pystray.MenuItem("Start with Windows", self.toggle_startup, checked=lambda _: startup_enabled()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self.quit),
            ),
        )

    def toggle_enabled(self, _icon, _item) -> None:
        self.enabled = not self.enabled
        self.refresh_icon()

    def toggle_startup(self, _icon, _item) -> None:
        set_startup(not startup_enabled())

    def quit(self, _icon, _item) -> None:
        self.stop.set()
        pids = spotify_pids()
        if pids and self.muted:
            set_spotify_mute(pids, False)
        self.icon.stop()

    def refresh_icon(self, title: str | None = None) -> None:
        if not self.enabled:
            state, text = "off", "Spotify Ad Muter: off"
        elif self.muted:
            state, text = "muting", "Spotify Ad Muter: ad muted"
        else:
            state, text = "on", "Spotify Ad Muter: on"
        if title:
            text = f"{text}\n{title}"
        self.icon.icon = ICONS[state]
        self.icon.title = text[:127]

    def worker(self, icon: pystray.Icon) -> None:
        comtypes.CoInitialize()
        icon.visible = False
        try:
            self.media = SpotifyMedia()
        except Exception:
            self.media = None
        while not self.stop.is_set():
            try:
                self.poll(icon)
            except Exception:
                self.stop.wait(IDLE_POLL_SECONDS)

    def poll(self, icon: pystray.Icon) -> None:
        pids = spotify_pids()
        if not pids:
            icon.visible = False
            self.muted = True
            self.stop.wait(IDLE_POLL_SECONDS)
            return

        icon.visible = True
        title = spotify_title(pids)
        try:
            media = self.media.read() if self.media else None
        except Exception:
            media = None
        should_mute = self.enabled and is_ad(title, media)
        if should_mute or self.muted:
            set_spotify_mute(pids, should_mute)
        self.muted = should_mute
        self.refresh_icon(title)
        self.stop.wait(POLL_SECONDS)

    def run(self) -> None:
        self.icon.run(setup=lambda icon: threading.Thread(target=self.worker, args=(icon,), daemon=True).start())


def main() -> None:
    mutex = win32event.CreateMutex(None, False, f"Global\\{APP_NAME}")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return
    AdMuter().run()
    del mutex


if __name__ == "__main__":
    main()
