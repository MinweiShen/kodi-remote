#!/bin/bash
# Run on the Pi, from the transferred checkout: sudo bash scripts/install.sh
set -euo pipefail
if [[ $(id -u) != 0 ]]; then
  echo '请使用 sudo bash scripts/install.sh' >&2
  exit 1
fi
if [[ $(uname -s) != Linux ]]; then
  echo '此安装脚本仅适用于 Linux Raspberry Pi。' >&2
  exit 1
fi
app_user=pi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target_dir=/home/pi/apps/kodi-browser-remote
config_file=/etc/kodi-remote.json
secret_file=/etc/kodi-remote.secret
id "$app_user" >/dev/null
# Show existing machine notes when present; fresh installations need no local notes.
for notes in /home/pi/README.md /home/pi/README-PROXY.md; do
  if [[ -f $notes ]]; then
    cat "$notes"
  fi
done
echo '安装系统依赖；沿用当前 apt 网络配置。'
apt-get install -y python3-aiohttp python3-evdev
install -d -o "$app_user" -g "$app_user" "$target_dir/kodi_remote/web"
if [[ $source_dir != "$target_dir" ]]; then
  install -m 0644 "$source_dir"/kodi_remote/*.py "$target_dir/kodi_remote/"
  install -m 0644 "$source_dir"/kodi_remote/web/* "$target_dir/kodi_remote/web/"
fi
chown -R "$app_user:$app_user" "$target_dir"
modprobe uinput
printf '%s\n' uinput > /etc/modules-load.d/kodi-remote.conf
install -m 0644 "$source_dir/scripts/70-uinput.rules" /etc/udev/rules.d/70-uinput.rules
usermod -aG input "$app_user"
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=misc
if [[ ! -e $secret_file ]]; then
  (umask 027; /usr/bin/python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$secret_file")
fi
chown "root:$app_user" "$secret_file"
chmod 0640 "$secret_file"
if [[ ! -e $config_file ]]; then
  install -m 0644 "$source_dir/config.example.json" "$config_file"
fi
install -m 0644 "$source_dir/scripts/kodi-remote.service" /etc/systemd/system/kodi-remote.service
systemctl daemon-reload
systemctl enable kodi-remote.service
systemctl restart kodi-remote.service
systemctl --no-pager --full status kodi-remote.service
echo '安装完成。默认入口 http://192.168.0.114:8091/；不会关闭旧的 8090 触控板。'
echo '在 Pi 本机执行 sudo cat /etc/kodi-remote.secret 查看访问密钥，不要复制到项目文件或聊天。'
echo '若页面显示 Kodi 不可用，请按 README.md 开启“允许本机应用程序远程控制”。'
