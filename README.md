# Spotify Ad Muter

A tiny Windows tray app that mutes Spotify while an ad is playing and unmutes it when your music comes back. Only Spotify is muted; every other app keeps its sound.

## Download

1. Grab `SpotifyAdMuter.exe` from the [latest release](https://github.com/laguileraab/SpotifyAdMuter/releases/latest).
2. Put it anywhere (for example `Documents\SpotifyAdMuter`) and double-click it.

No installation needed. Windows SmartScreen may warn you because the exe isn't code-signed; click **More info** then **Run anyway**.

## Usage

The app stays hidden in the background and its tray icon appears only while Spotify is running.

| Icon | Meaning |
| --- | --- |
| Green | On, waiting for ads |
| Red | An ad is playing and Spotify is muted |
| Grey | Turned off |

Right-click the icon for:

- **Enabled**: turn ad muting on/off (double-clicking the icon does the same).
- **Start with Windows**: launch automatically when you log in.
- **Quit**: exit (Spotify is unmuted first).

Windows may tuck new tray icons into the hidden-icons area (the `^` arrow). Drag it onto the taskbar to keep it visible.

## How it works

While a song plays, the Spotify desktop window title is `Artist - Song`. During ads it changes to things like `Advertisement`, `Spotify`, or the advertiser's name. When the title no longer looks like a song (and Spotify isn't simply paused), the app mutes Spotify's own audio session in the Windows volume mixer.

If an ad's title happens to contain ` - `, it won't be detected. Feel free to open an issue with the title you saw.

## Running from source

Requires Python 3.10+ on Windows.

```powershell
pip install -r requirements.txt
pythonw spotify_ad_muter.py
```

To build the exe yourself:

```powershell
.\build.ps1
```

The output is `dist\SpotifyAdMuter.exe`.

## License

MIT
