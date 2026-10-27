# Pi deployment — 2026-10-27

- Service: `kodi-remote.service`, enabled at boot, running as `pi` with input-group access.
- URL: `http://192.168.0.114:8091/`; old `remote-touchpad.service` remains on 8090.
- Kodi: 21.3; its JSON-RPC port 9090 remains bound to loopback only. No proxy settings changed.
- Installed code: `/home/pi/apps/kodi-browser-remote`; Git source: `/home/pi/src/kodi-browser-remote`.
- Configuration: `/etc/kodi-remote.json`; access key: `/etc/kodi-remote.secret`, root:pi 0640. Credentials are not recorded here.
- Dependencies installed from Debian: git, python3-aiohttp 3.11.16, python3-evdev 1.9.1.

## Actual device checks

Passed with `scripts/smoke_pi.py`:

- uinput REL_X/REL_Y, right click down/up, wheel, release after WebSocket disconnect.
- Authenticated real service / Kodi connection.
- Silent temporary 25-minute video: play/pause, absolute seek, all six ±10/60/600-second jumps (within one second of expected positions).
- Software volume and mute, two audio streams, external subtitles.
- Previous/next episode in a local folder and missing-episode feedback.
- Standard Kodi keyboard dialog accepted the Unicode text `流浪地球 2` and closed successfully.

Kodi GBM exclusively grabs mouse devices, so kernel-event validation ran briefly with Kodi stopped, followed by restarting Kodi. Playback tests restored original volume/mute, returned Kodi to Home (no video had been playing before the test), and removed all temporary videos.

The first real folder test exposed Kodi's refusal to list directories outside registered media sources. Production now enumerates only the current video's direct parent folder using ordinary pi-user filesystem access, and rejects symlink escapes. A regression test covers this case.

Physical iPhone sensitivity calibration and visual confirmation of Chinese glyphs remain manual checks. See `TESTING.md`.

## Navigation-first UI revision

The main screen now contains navigation controls. The touchpad, explicit left/right clicks and drag lock are in the overlay menu’s Mouse group. Switching groups or closing the menu releases the mouse. The deployment updates static assets without changing the access key or restarting the backend.
