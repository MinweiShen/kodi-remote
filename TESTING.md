# Kodi 浏览器遥控器：运行、部署与测试

实现代码位于 `kodi_remote/`，设计位于 `.scratch/kodi-browser-remote/spec.md`。
新服务已于 **2026-10-27** 部署，使用 **8091**，旧触控板 **8090** 保留。Pi 实际环境：Debian 13.7 ARM64、Python 3.13、aiohttp 3.11.16、evdev 1.9.1、Kodi 21.3。局域网页面、鉴权及真实 Kodi/uinput 联调已通过；iPhone Safari 的实际触感和电视上的字形显示仍需用户手动验收。

2026-10-27 本地验证结果：16 项 Python 测试、2 项 Node 测试通过，Python/JavaScript 和安装脚本语法检查通过。Chrome 已验证中文提交、暂停、+1 分钟跳转、停止后隐藏进度、覆盖菜单；320 / 375 / 414 / 768 像素宽度均无横向溢出。375×812 视口中，触控板未播放时高 752 像素，播放时高 663 像素，菜单覆盖同一区域而不缩小它。

界面记录：[主界面](.scratch/kodi-browser-remote/screenshots/main.jpg)、[播放菜单](.scratch/kodi-browser-remote/screenshots/menu.jpg)。截图使用模拟视频；右侧粉色浮动图标属于测试浏览器扩展，不是遥控器界面。

实机结果：内核输入设备发出了预期的 `REL_X=60 / REL_Y=30`，右键、滚轮与断线释放通过。无声临时视频的播放/暂停、绝对跳转、±10/60/600 秒、软件音量/静音、双音轨、外挂字幕、文件夹上下集和缺集提示均通过；标准 Kodi 输入对话框接受了“流浪地球 2”。测试结束后恢复音量/静音并返回首页，临时视频已清理。播放器暂停定位允许 3 秒以内的解码/关键帧偏差，本次六档跳转均在 1 秒以内。

本次实机发现 Kodi 会拒绝列出未注册为媒体源的目录；上下集功能已改为由 Pi 服务枚举当前视频父目录，排除越界符号链接。手机仍不能提交任意目录或任意文件路径。

## 1. 先在 Mac 预览界面

在项目目录执行：

```sh
cd /Users/bytedance/Documents/ChatGPT/pi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m kodi_remote --demo
```

浏览器打开 `http://localhost:8091/`，密钥填 `demo`。

- 演示模式使用模拟视频、字幕和音轨，不连接真实 Kodi，不打开 uinput。
- 可测试暂停、六种跳转、拖动进度、停止后隐藏进度、覆盖菜单、上下集。
- “菜单 → 导航 → 确认”模拟 Kodi 打开搜索框，再到“输入”提交中文。
- “停止”后演示视频不会自动重新打开；需要重新启动演示服务恢复初始视频。
- 演示模式只监听本机，不能用 iPhone 访问 Mac 的局域网地址。真实鼠标手感与 iOS 输入法需要第 4 节实机测试。
- `Ctrl+C` 停止服务。

如果当前 Python 已安装 aiohttp，也可以直接执行 `python3 -m kodi_remote --demo`。

## 2. 自动检查

从项目根目录运行：

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/web.test.mjs
node --check kodi_remote/web/app.js
bash -n scripts/install.sh
```

Python 测试会在回环地址创建临时 HTTP / WebSocket 服务，需允许本机端口监听。测试覆盖：集号与缺集、多版本候选、位移加速和小数保留、访问鉴权和同源限制、旧视频指令拒绝、中文输入目标、跨设备接管、断线释放、取消未发送指令、Kodi 断线不重放请求。Node 测试不需要 `npm install`。

### 在 Pi 重复真实设备测试

`scripts/smoke_pi.py` 默认执行播放测试：生成临时无声长视频，测试完清理并恢复原播放位置及音量/静音。如果没有正在播放的视频，则返回首页。运行时请关闭手机遥控页面，避免多个控制器争用：

```sh
cd /home/pi/src/kodi-browser-remote
sudo -u pi /usr/bin/python3 scripts/smoke_pi.py --mode playback
```

GBM Kodi 会独占鼠标设备，读取内核事件的测试需要短暂停止 Kodi。确认当前没有需要保留的播放后，逐条执行下面三条命令；无论中间测试是否成功，都执行最后一条以恢复 Kodi：

```sh
sudo systemctl stop kodi
sudo -u pi /usr/bin/python3 scripts/smoke_pi.py --mode input
sudo systemctl start kodi
```

脚本在 Pi 本机读取访问密钥，不打印密钥，也不需要将密钥复制到测试文件。测试使用已安装的 FFmpeg。

## 3. 安装到 Pi

### 3.1 连接并检查现有说明

回到与 Pi 同一局域网后使用 `ssh pi@192.168.0.114`。不在同一网络时，使用 Pi Connect 的 Remote shell；设备必须在线。

在 Pi 上先执行：

```sh
cat /home/pi/README.md /home/pi/README-PROXY.md
uname -m
cat /etc/os-release
systemctl status kodi remote-touchpad --no-pager
```

按 README 使用现有代理，不修改 v2rayA 配置。安装脚本使用当前 apt 配置，不自行改代理。

### 3.2 从 Mac 传输版本库

以下命令要求 Mac 与 Pi 可直接 SSH 连通。Git bundle 包含本地提交，便于 Pi 上追踪版本：

```sh
cd /Users/bytedance/Documents/ChatGPT/pi
git bundle create /tmp/kodi-browser-remote.bundle codex/kodi-browser-remote
scp /tmp/kodi-browser-remote.bundle pi@192.168.0.114:/home/pi/kodi-browser-remote.bundle
```

在 Pi 上首次安装：

```sh
mkdir -p /home/pi/src
git clone -b codex/kodi-browser-remote /home/pi/kodi-browser-remote.bundle /home/pi/src/kodi-browser-remote
cd /home/pi/src/kodi-browser-remote
git log -1 --oneline
sudo bash scripts/install.sh
```

如果 Pi 没有 git，按现有 apt/代理说明先安装 `git`。如果目标源码目录已存在，先检查 `git status`；后续更新使用 `git fetch /home/pi/kodi-browser-remote.bundle codex/kodi-browser-remote` 和 `git merge --ff-only FETCH_HEAD`，不要覆盖未提交改动。源码与运行目录分开，更新后重新执行安装脚本。

仅有 Pi Connect 终端时，先通过你已有的文件传输方式把 bundle 放到 Pi，再执行上述 Pi 命令；Pi Connect 终端本身不提供本项目的文件上传功能。

安装脚本会：安装 Debian 的 `python3-aiohttp` / `python3-evdev`，配置 uinput 设备权限，将程序复制到 `/home/pi/apps/kodi-browser-remote`，创建独立访问密钥，启用 `kodi-remote.service`。重复安装保留现有配置和密钥。不会停止旧 `remote-touchpad.service`。

### 3.3 开启 Kodi 的本机接口

电视上进入 Kodi **设置 → 服务 → 控制**，开启“允许本机应用程序远程控制”（英文通常为 **Allow remote control from applications on this system**）。如选项不可见，先切换设置级别到高级/专家。保留“允许其他系统上的应用程序远程控制”为关闭。

本服务连接 `ws://127.0.0.1:9090/jsonrpc`，不用 Kodi HTTP 网页服务，也不与 qBittorrent 的 8080 争用端口。检查：

```sh
ss -lntp '( sport = :9090 or sport = :8091 )'
sudo systemctl status kodi-remote --no-pager
journalctl -u kodi-remote -n 50 --no-pager
```

9090 应只允许本机访问。若 Kodi 使用其他 TCP 端口，修改 `/etc/kodi-remote.json` 中的 `kodi_url`，仍使用回环地址。若 Pi 局域网地址变化，修改同文件的 `host`。改后执行 `sudo systemctl restart kodi-remote`。

接口设置依据：[Kodi 官方 JSON-RPC 文档](https://kodi.wiki/view/JSON-RPC_API)。具体皮肤和安装版本的设置名称可能略有不同。

### 3.4 iPhone 连接

1. iPhone 与 Pi 连接同一家庭网络。
2. Safari 打开 `http://192.168.0.114:8091/`。
3. 在 Pi 本机执行 `sudo cat /etc/kodi-remote.secret` 查看密钥，手动填入手机登录框。不要将密钥提交到 Git、发到聊天或放入 URL 查询参数。
4. 顶部应显示“已连接”或当前播放状态。如显示“Kodi 不可用”，先检查第 3.3 节。

会话有效期 12 小时。当前方案使用可信家庭局域网 HTTP，不应做公网端口转发。

## 4. iPhone + 电视验收清单

建议按此顺序，每项观察电视上的实际效果：

| 操作 | 预期结果 |
| --- | --- |
| 未播放时打开网页 | 只有 Kodi 信息和触控板，没有进度条或底部按钮栏 |
| 单指慢划、快划 | 慢划能精确选择；快划一次能跨越大部分/整个屏幕 |
| 菜单 → 设置 → 灵敏度 | 太慢就提高倍率；开启加速后快划距离进一步扩大；刷新后偏好保留 |
| 单指轻点、双指轻点、双指滑动 | 分别是左键、右键、滚轮；滚动结束不产生点击 |
| 菜单 → 设置 → 开启拖拽 | 菜单关闭后移动即拖拽；再次开菜单释放，不出现卡住的按键 |
| 打开操作菜单并连续点按钮 | 面板覆盖触控板，大按钮易点；菜单内部滚动不移动电视光标；连续操作不关闭菜单 |
| 在 Kodi 播放长于 20 分钟的本地视频 | 片名与进度出现；暂停时进度保留且时钟停止 |
| 在视频中部点击 ±10 秒 / ±1 分钟 / ±10 分钟 | 每次偏移对应时间，菜单保持打开；关键帧造成的小偏差可接受 |
| 拖动顶部进度条 | 拖动只预览，松手执行一次跳转；后台状态更新不抢回滑块 |
| 菜单 → 播放 → 停止 | 进度区完全消失，触控板自动变大；播放/跳转按钮禁用 |
| Kodi 打开搜索对话框 → 网页菜单 → 输入 | 输入“流浪地球 2”，选字完成后“发送并确认”；电视内容正确，字体无方框 |
| 输入有内容的对话框、取消后重开 | 验证整段替换语义；不支持的内嵌/插件输入框不盲发文字 |
| 字幕开关、字幕轨道、音轨 | 电视与选项状态一致；没有字幕/其他音轨时相应选项不可用 |
| 音量和静音 | Kodi 软件音量反馈正确；音频直通时使用电视/功放调节 |
| 同文件夹 `S01E09` → 下一集 | 播放 `S01E10`，无需预先建队列；缺集不跳过，多版本显示候选 |
| 另一手机/浏览器打开 → 设置 → 接管 | 旧设备失去控制、鼠标按键释放；新设备可控制 |
| 锁屏、切后台、断 Wi-Fi、重启 Kodi 后恢复 | 状态重新同步；没有重复跳转、幽灵点击或持续拖拽 |

真实电视鼠标跨屏倍率、Kodi 字体、具体皮肤输入框和解码器跳转精度只能通过实机确认，演示测试不能代替。

## 5. 停用和回退

新服务和旧服务使用独立端口。需要回退时在 Pi 上执行：

```sh
sudo systemctl disable --now kodi-remote
sudo systemctl start remote-touchpad
```

随后使用原来的 8090 触控板入口与原密钥。新程序、配置和密钥都保留，可随时重新启用 `kodi-remote`。不要删除共享的 uinput 规则，否则旧触控板也会受影响。
