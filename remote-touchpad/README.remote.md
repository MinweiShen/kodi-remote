# mypi 使用入口

代理使用说明（网页管理、终端、qBittorrent、Node 服务及排查）：

```bash
less ~/README-PROXY.md
```

代理管理：http://192.168.0.114:2017/
下载器管理：http://192.168.0.114:8080/

当前终端按需开启代理：

```bash
source ~/proxy-env.sh
```

详细说明见 README-PROXY.md。管理密码请向设备管理员获取。

## 动漫订阅与下载（ANI-RSS）

安装日期：2026-10-27（北京时间）

- ANI-RSS 管理：http://192.168.0.114:7789/
- 服务：ani-rss.service（已启用开机启动）
- 程序：/home/pi/ani-rss/ani-rss.jar
- 配置：/home/pi/ani-rss/config/config.v2.json（含密钥，权限 600；不要公开）
- 番剧目录：/home/pi/Downloads/Anime/${title}/Season ${season}
- Kodi 视频源 Anime 已指向 /home/pi/Downloads/Anime/
- 剧场版目录：/home/pi/Downloads/Anime/Movies/${title}
- 下载器：qBittorrent Web API http://127.0.0.1:8080，使用 API Key；密钥不写入本文
- 网络：ANI-RSS 使用本机 HTTP 代理 127.0.0.1:1081 访问外部元数据与 RSS
- 管理员用户名：admin；密码另行保管，不写入本文

ANI-RSS v3.2.53 要求 qBittorrent API Key。Debian 13 自带的 qBittorrent 5.1.0 不支持该功能，因此已从官方 release-5.2.4 源码编译无界面版本到 /usr/local/bin/qbittorrent-nox。systemd override 位于 /etc/systemd/system/qbittorrent-nox.service.d/local-build.conf；Debian 原包仍保留作为回退。切换前备份位于 /home/pi/backups/qbittorrent-before-5.2.4/。

常用检查：

```bash
systemctl status ani-rss qbittorrent-nox kodi metube --no-pager
journalctl -u ani-rss -n 100 --no-pager
```

## iPhone 网页触控板（Remote Touchpad）

安装日期：2026-10-27（北京时间）

- 入口：`http://192.168.0.114:8090/`（需要访问密钥；完整 URL 保存在服务启动日志中）
- 服务：`remote-touchpad.service`（已启用开机启动）
- 程序：`/home/pi/.local/bin/remote-touchpad`
- 启动脚本：`/usr/local/libexec/remote-touchpad-start`
- 访问密钥：`/etc/remote-touchpad.secret`（不要公开）
- uinput 规则：`/etc/udev/rules.d/70-uinput.rules`
- 本服务使用 Linux uinput，适配当前 Kodi GBM/DRM 独占会话；无需 X11 或 Wayland。
- 服务只监听 Pi 的局域网地址 `192.168.0.114:8090`，未配置 TLS，仅限可信家庭局域网使用。

常用检查：

```bash
systemctl status remote-touchpad --no-pager
journalctl -u remote-touchpad -n 100 --no-pager
ss -lntp '( sport = :8090 )'
```

查看当前完整访问 URL：

```bash
secret=$(sudo cat /etc/remote-touchpad.secret)
printf 'http://192.168.0.114:8090/#%s\n' "$secret"
```
