# Raspberry Pi services

Connect with `ssh pi@192.168.0.114`.

## Kodi browser remote (deployed 2026-10-27)

Native Python service and buildless iPhone UI in `kodi_remote/`. The main screen contains Kodi status, a progress bar while a video is active, and large navigation buttons. Mouse controls, playback, text input and settings live in an overlay menu. Mouse input uses uinput; Unicode text, playback, subtitles and audio use local Kodi JSON-RPC. Previous/next episode searches the current local folder.

- Live interface: http://192.168.0.114:8091/ ; `kodi-remote.service` is enabled at boot. Existing 8090 remote-touchpad stays available.
- Runtime: `/home/pi/apps/kodi-browser-remote`; versioned source: `/home/pi/src/kodi-browser-remote`; config: `/etc/kodi-remote.json`; access key: `/etc/kodi-remote.secret` (do not print in logs or commit).
- Real Pi validation passed on Kodi 21.3: uinput movement/click/scroll/release, six seek offsets, pause, progress, volume/mute, subtitle/audio tracks, folder episodes, and Unicode dialog submission. iPhone hand feel still needs the user's physical test.
- Local UI demo: `python3 -m kodi_remote --demo`, then open http://localhost:8091/ with demo key `demo` (requires aiohttp).
- Installation, test checklist and rollback: [TESTING.md](TESTING.md).
- Design: [.scratch/kodi-browser-remote/spec.md](.scratch/kodi-browser-remote/spec.md).
- No SSH passwords, production access keys or Kodi credentials are stored in this repository.

## MeTube

Installed natively on 2026-10-27, without Docker.

- Web interface: http://192.168.0.114:8081/
- Downloads (video and audio): `/home/pi/Downloads`
- Application: `/home/pi/apps/metube`
- Python environment: `/home/pi/apps/metube/.venv`
- Configuration: `/home/pi/apps/metube/metube.env`
- Queue, history and cookies: `/home/pi/.local/share/metube`
- Service: `/etc/systemd/system/metube.service`, running as `pi`, enabled at boot
- Node.js build runtime: `/home/pi/.local/opt/node`

Commands to run on the Pi:

```sh
systemctl status metube
sudo systemctl restart metube
sudo systemctl stop metube
journalctl -u metube -n 50 --no-pager
```

The installation uses the upstream frontend build and `uv sync --frozen --no-dev` for Python dependencies. FFmpeg is installed from Debian/Raspberry Pi repositories. The Python environment includes yt-dlp and Deno for JavaScript challenges.

After changing `metube.env`, restart the service. Download availability depends on connectivity and site/account requirements. Bilibili cookies were verified active on 2026-10-27; do not print their contents.

## Proxy

Read `/home/pi/README.md` and `/home/pi/README-PROXY.md` on the Pi before network changes. The existing v2rayA service provides local HTTP `http://127.0.0.1:1081` and SOCKS5 `socks5h://127.0.0.1:1080`. It is used per application, not automatically by every SSH shell or systemd service.

MeTube has an optional `Pi proxy` preset under Advanced Options. Select it for YouTube and other sites requiring the proxy; without it, downloads remain direct. The preset is configured in `metube.env` via `YTDL_OPTIONS_PRESETS`. Do not disable MeTube's private-address protection to work around DNS when the explicit proxy handles domain resolution.
