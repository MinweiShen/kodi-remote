# Raspberry Pi services

Connect with `ssh pi@192.168.0.114`.

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
