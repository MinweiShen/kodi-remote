# Project context

- This project primarily concerns work on the user's Raspberry Pi. In this project, “pi” refers to that Raspberry Pi.
- Connect with `ssh pi@192.168.0.114` (user: `pi`). The shorthand `ssh pi` did not resolve in this environment. Use the explicit address for remote inspection and authorized work.
- Verified on 2026-10-27: the Raspberry Pi runs Debian GNU/Linux 13 (trixie), architecture `aarch64` (ARM64). Docker was not found on the login PATH. Recheck before installation work.
- Do not store SSH passwords in project files.
- The Raspberry Pi already has a proxy. Before asking the user for proxy details or changing network settings, read the README on the Pi and follow its documented setup. Check remote README/service notes first for existing configuration in general.
- Remote documentation entry points: `/home/pi/README.md` and `/home/pi/README-PROXY.md`. Existing v2rayA proxy endpoints are HTTP `http://127.0.0.1:1081` and SOCKS5 `socks5h://127.0.0.1:1080`, local to the Pi. SSH shells and systemd services do not automatically inherit this proxy. Do not change v2rayA core configuration or enable the old `v2ray.service`.
- MeTube is installed natively without Docker, managed by `metube.service`, and available at `http://192.168.0.114:8081/`. Downloads go to `/home/pi/Downloads`. See `README.md` for configuration and maintenance paths.
- Treat the local workspace as a place for project notes, configuration, and scripts; check the remote system before assuming its architecture, OS, or installed tools.

## Agent skills

### Issue tracker

Issues are tracked as local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Triage uses the default five-role vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See `docs/agents/domain.md`.
