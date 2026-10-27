import asyncio
import hmac
import json
import math
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

import aiohttp
from aiohttp import web

from .demo import DemoKodi
from .episodes import neighbors, playable, local_videos
from .mouse import Mouse
from .rpc import KodiError, KodiRPC

STATIC = Path(__file__).with_name("web")
NAV = {"up": "Up", "down": "Down", "left": "Left", "right": "Right", "select": "Select",
       "back": "Back", "home": "Home", "context": "ContextMenu"}
PROPERTIES = ["time", "totaltime", "speed", "canseek", "subtitleenabled", "subtitles",
              "audiostreams", "currentsubtitle", "currentaudiostream"]


def seconds(value):
    return value.get("hours", 0) * 3600 + value.get("minutes", 0) * 60 + value.get("seconds", 0)


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("数值超出范围")
    return value


class Remote:
    def __init__(self, config):
        self.config = config
        self.secret = config["secret"]
        self.demo = config.get("demo", False)
        self.sessions = {}
        self.attempts = defaultdict(deque)
        self.clients = {}
        self.controller = None
        self.mouse = None
        self.rpc = None
        self.tasks = []
        self.changed = asyncio.Event()
        self.input_target = None
        self.state = {"online": False, "active": False, "generation": 0, "demo": self.demo}
        self.current_file = None
        self.choices = {}

    def notify(self, method, data):
        if method == "Input.OnInputRequested":
            self.input_target = {"title": data.get("title", "Kodi 输入"), "type": data.get("type"),
                                 "id": secrets.token_urlsafe(12)}
        elif method in ("Input.OnInputFinished", "remote.disconnected"):
            self.input_target = None
        if method == "remote.disconnected" and self.mouse:
            self.mouse.release()
        self.changed.set()

    async def start(self, app):
        self.mouse = Mouse(self.demo)
        session = aiohttp.ClientSession()
        self.http = session
        self.rpc = DemoKodi(self.notify) if self.demo else KodiRPC(session, self.config["kodi_url"], self.notify)
        self.tasks = [asyncio.create_task(self.rpc.run()), asyncio.create_task(self.poll()),
                      asyncio.create_task(self.watchdog())]
        yield
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for ws in list(self.clients):
            await ws.close()
        await self.rpc.close()
        await session.close()
        self.mouse.close()

    def same_origin(self, request):
        origin = request.headers.get("Origin", "")
        return origin == f"{request.scheme}://{request.host}"

    def session(self, request):
        key = request.cookies.get("kodi_remote", "")
        if self.sessions.get(key, 0) <= time.monotonic():
            raise web.HTTPUnauthorized(text="请重新输入访问密钥")
        return key

    async def login(self, request):
        if not self.same_origin(request) or request.content_type != "application/json":
            raise web.HTTPForbidden()
        now = time.monotonic()
        attempts = self.attempts[request.remote]
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 5:
            raise web.HTTPTooManyRequests(text="尝试过多，请一分钟后重试")
        attempts.append(now)
        data = await request.json()
        supplied = data.get("secret", "") if isinstance(data, dict) else ""
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), self.secret.encode()):
            raise web.HTTPUnauthorized(text="访问密钥不正确")
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        token = secrets.token_urlsafe(32)
        self.sessions[token] = now + 12 * 3600
        response = web.json_response({"ok": True})
        response.set_cookie("kodi_remote", token, httponly=True, samesite="Strict", max_age=12 * 3600,
                            secure=request.secure)
        return response

    async def get_state(self, request):
        self.session(request)
        return web.json_response(self.public_state())

    def public_state(self):
        return {**self.state, "input": self.input_target}

    async def broadcast(self):
        for ws in list(self.clients):
            try:
                await asyncio.wait_for(ws.send_json({"type": "state", "state": self.public_state(),
                                                     "control": self.controller is ws}), 1)
            except (ConnectionError, RuntimeError, asyncio.TimeoutError):
                await ws.close()

    async def refresh(self):
        online = self.rpc.connected
        data = {"online": online, "active": False, "generation": self.state["generation"], "demo": self.demo}
        file = None
        if online:
            players = await self.rpc.call("Player.GetActivePlayers")
            video = next((p for p in players if p["type"] == "video"), None)
            app = await self.rpc.call("Application.GetProperties", properties=["volume", "muted"])
            data.update(app)
            if video:
                pid = video["playerid"]
                item = (await self.rpc.call("Player.GetItem", playerid=pid, properties=["file", "title"]))["item"]
                props = await self.rpc.call("Player.GetProperties", playerid=pid, properties=PROPERTIES)
                file = item.get("file", "")
                data.update(active=True, playerid=pid, title=item.get("title") or item.get("label") or Path(file).name,
                            time=seconds(props["time"]), duration=seconds(props["totaltime"]),
                            speed=props.get("speed", 0), canseek=props.get("canseek", False),
                            subtitles=props.get("subtitles", []), audio=props.get("audiostreams", []),
                            subtitle=props.get("currentsubtitle", {}).get("index", -1),
                            audiostream=props.get("currentaudiostream", {}).get("index", -1),
                            subtitleenabled=props.get("subtitleenabled", False))
        if file != self.current_file:
            data["generation"] += 1
            self.choices.clear()
        self.current_file = file
        self.state = data

    async def poll(self):
        while True:
            self.changed.clear()
            try:
                await self.refresh()
            except (KodiError, aiohttp.ClientError, KeyError, TypeError):
                self.input_target = None
                if self.current_file is not None:
                    self.state["generation"] += 1
                self.current_file = None
                self.choices.clear()
                self.state = {"online": False, "active": False, "generation": self.state["generation"], "demo": self.demo}
            await self.broadcast()
            try:
                await asyncio.wait_for(self.changed.wait(), 1)
            except asyncio.TimeoutError:
                pass

    async def watchdog(self):
        while True:
            await asyncio.sleep(2)
            now = time.monotonic()
            for ws, client in list(self.clients.items()):
                if now - client["seen"] > 15 or self.sessions.get(client["session"], 0) <= now:
                    if self.controller is ws:
                        self.mouse.release()
                    client["revoked"] = True
                    if client["operation"]:
                        client["operation"].cancel()
                    await ws.close()

    async def player(self, message):
        if not self.state.get("active") or message.get("generation") != self.state["generation"]:
            raise KodiError("播放项目已改变，请等待状态更新")
        players = await self.rpc.call("Player.GetActivePlayers")
        pid = next((p["playerid"] for p in players if p["type"] == "video"), None)
        if pid is None:
            raise KodiError("当前没有播放视频")
        item = await self.rpc.call("Player.GetItem", playerid=pid, properties=["file"])
        if item["item"].get("file") != self.current_file:
            self.changed.set()
            raise KodiError("已切换视频，本次操作已取消")
        return pid

    def directory_files(self, result, parent):
        root = Path(parent).resolve()
        files = []
        for item in result.get("files", []):
            path = item.get("file", "")
            if item.get("filetype") == "file" and path.startswith("/") and playable(path):
                resolved = Path(path).resolve()
                if resolved.parent == root:
                    files.append(str(resolved))
        return files

    async def episode(self, message):
        await self.player(message)
        if not self.current_file or not self.current_file.startswith("/"):
            raise KodiError("上下集仅支持本机视频文件夹")
        parent = str(Path(self.current_file).resolve().parent)
        if self.demo:
            result = await self.rpc.call("Files.GetDirectory", directory=parent, media="video")
            files = self.directory_files(result, parent)
        else:
            # Kodi can play a local file while refusing JSON-RPC directory listing outside
            # registered media sources. Scope OS enumeration to the active file's parent.
            try:
                files = await asyncio.to_thread(local_videos, parent)
            except OSError as exc:
                raise KodiError("无法读取当前视频文件夹，请检查 pi 用户的读取权限") from exc
        if message["action"] == "choose_episode":
            target = self.choices.get(message.get("choice"))
            if target not in files:
                raise KodiError("候选文件已失效，请重新打开上下集")
        else:
            direction = message.get("direction")
            if direction not in (-1, 1):
                raise ValueError("无效的上下集方向")
            target, candidates, reason = neighbors(self.current_file, files, direction)
            if not target:
                self.choices = {secrets.token_urlsafe(12): path for path in candidates}
                return {"choices": [{"id": key, "name": Path(path).name} for key, path in self.choices.items()], "reason": reason}
        # Revalidate after directory I/O; never stop the current video before opening the target.
        await self.player(message)
        if not self.demo and not Path(target).is_file():
            raise KodiError("视频文件已不存在")
        await self.rpc.call("Player.Open", item={"file": target}, options={"resume": False})
        self.choices.clear()
        return {"message": "已切换视频"}

    async def command(self, message, client):
        action = message.get("action")
        if action == "move":
            samples = message.get("samples", [])
            if not isinstance(samples, list) or len(samples) > 64:
                raise ValueError("位移数据过多")
            for sample in samples:
                if not isinstance(sample, list) or len(sample) != 3:
                    raise ValueError("无效位移")
                dx, dy, dt = [number(v, -2000, 2000) for v in sample]
                number(dt, 1, 100)
                self.mouse.move(dx, dy, dt, client["sensitivity"], client["acceleration"])
            return {}
        if action == "gesture_end":
            self.mouse.speed = 0
            return {}
        if action == "preferences":
            client["sensitivity"] = number(message.get("sensitivity"), 1, 8)
            if not isinstance(message.get("acceleration"), bool):
                raise ValueError("无效的加速设置")
            client["acceleration"] = message["acceleration"]
            return {}
        if action in ("click", "button"):
            button = message.get("button", "left")
            if button not in ("left", "right"):
                raise ValueError("无效按键")
            if action == "click":
                self.mouse.button(button, True)
                self.mouse.button(button, False)
            else:
                if not isinstance(message.get("down"), bool):
                    raise ValueError("无效按键状态")
                self.mouse.button(button, message["down"])
            return {}
        if action == "scroll":
            steps = number(message.get("steps"), -20, 20)
            if int(steps) != steps:
                raise ValueError("滚动量必须为整数")
            self.mouse.scroll(int(steps))
            return {}
        if action == "release":
            self.mouse.release()
            return {}
        if action == "nav":
            method = NAV.get(message.get("key"))
            if not method:
                raise ValueError("无效导航键")
            await self.rpc.call("Input." + method)
        elif action == "text":
            text = message.get("text")
            if not isinstance(text, str) or len(text) > 4096:
                raise ValueError("文字过长或格式错误")
            if not self.input_target or self.input_target["type"] != "keyboard":
                raise KodiError("请先在 Kodi 中重新打开文字输入框；仅支持普通文字对话框")
            if message.get("input_id") != self.input_target["id"]:
                raise KodiError("文字输入目标已改变，请确认当前对话框后重新发送")
            await self.rpc.call("Input.SendText", text=text, done=True)
            self.input_target = None
        elif action == "volume":
            props = await self.rpc.call("Application.GetProperties", properties=["volume"])
            delta = number(message.get("delta"), -10, 10)
            await self.rpc.call("Application.SetVolume", volume=int(max(0, min(100, props["volume"] + delta))))
        elif action == "mute":
            await self.rpc.call("Application.SetMute", mute="toggle")
        elif action in ("episode", "choose_episode"):
            return await self.episode(message)
        elif action in ("playpause", "stop", "seek", "seek_to", "subtitle", "audio"):
            pid = await self.player(message)
            if action in ("playpause", "stop"):
                await self.rpc.call("Player.PlayPause" if action == "playpause" else "Player.Stop", playerid=pid)
            elif action in ("seek", "seek_to"):
                props = await self.rpc.call("Player.GetProperties", playerid=pid, properties=["canseek", "totaltime"])
                duration = seconds(props["totaltime"])
                if not props.get("canseek") or duration <= 0:
                    raise KodiError("当前视频无法跳转")
                if action == "seek":
                    delta = message.get("seconds")
                    if delta not in (-600, -60, -10, 10, 60, 600):
                        raise ValueError("无效的跳转步长")
                    value = {"seconds": delta}
                else:
                    t = int(number(message.get("seconds"), 0, duration))
                    value = {"time": {"hours": t // 3600, "minutes": t // 60 % 60, "seconds": t % 60}}
                await self.rpc.call("Player.Seek", playerid=pid, value=value)
            elif action == "subtitle":
                index = message.get("index")
                if index not in ("on", "off"):
                    if not isinstance(index, int) or isinstance(index, bool) or index not in [s["index"] for s in self.state.get("subtitles", [])]:
                        raise ValueError("无效字幕轨道")
                await self.rpc.call("Player.SetSubtitle", playerid=pid, subtitle=index, enable=index != "off")
            else:
                index = message.get("index")
                if not isinstance(index, int) or isinstance(index, bool) or index not in [s["index"] for s in self.state.get("audio", [])]:
                    raise ValueError("无效音轨")
                await self.rpc.call("Player.SetAudioStream", playerid=pid, stream=index)
        else:
            raise ValueError("不支持的操作")
        return {"message": "已发送"}

    async def websocket(self, request):
        session = self.session(request)
        if not self.same_origin(request):
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse(heartbeat=10, max_msg_size=32768)
        await ws.prepare(request)
        client = {"session": session, "seen": time.monotonic(), "sensitivity": 3, "acceleration": True,
                  "operation": None, "revoked": False}
        self.clients[ws] = client
        if self.controller is None:
            self.controller = ws
        await self.broadcast()
        try:
            async for raw in ws:
                if raw.type != aiohttp.WSMsgType.TEXT:
                    continue
                client["seen"] = time.monotonic()
                request_id = None
                try:
                    message = json.loads(raw.data)
                    if not isinstance(message, dict):
                        raise ValueError("无效请求")
                    request_id = message.get("id")
                    if message.get("action") == "heartbeat":
                        continue
                    if message.get("action") == "takeover":
                        old = self.controller
                        self.mouse.release()
                        self.controller = ws
                        client["revoked"] = False
                        if old is not None and old is not ws:
                            old_client = self.clients.get(old)
                            if old_client:
                                old_client["revoked"] = True
                                if old_client["operation"]:
                                    old_client["operation"].cancel()
                            await old.send_json({"type": "revoked"})
                        await self.broadcast()
                        result = {"message": "已接管"}
                    elif self.controller is not ws:
                        raise KodiError("另一设备正在控制，请先接管")
                    else:
                        client["operation"] = asyncio.create_task(self.command(message, client))
                        try:
                            result = await client["operation"]
                        except asyncio.CancelledError:
                            if client["revoked"]:
                                raise KodiError("控制已被接管，尚未发送的操作已取消")
                            raise
                        finally:
                            client["operation"] = None
                        if message.get("action") not in {"move", "scroll", "gesture_end", "heartbeat", "release", "preferences", "button", "click"}:
                            self.changed.set()
                    if request_id is not None:
                        await ws.send_json({"type": "result", "id": request_id, "ok": True, **result})
                except (ValueError, KeyError, TypeError, KodiError, aiohttp.ClientError) as exc:
                    await ws.send_json({"type": "result", "id": request_id, "ok": False, "error": str(exc)})
        finally:
            if client["operation"]:
                client["operation"].cancel()
            self.clients.pop(ws, None)
            if self.controller is ws:
                self.mouse.release()
                self.controller = None
            await self.broadcast()
        return ws


@web.middleware
async def headers(request, handler):
    response = await handler(request)
    response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "Referrer-Policy": "no-referrer",
                             "Content-Security-Policy": "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    return response


def create_app(config):
    app = web.Application(client_max_size=32768, middlewares=[headers])
    remote = Remote(config)
    app[web.AppKey("remote", Remote)] = remote
    # Also expose through an ordinary attribute for command-line diagnostics and tests.
    app.remote = remote
    app.cleanup_ctx.append(remote.start)
    app.router.add_post("/api/login", remote.login)
    app.router.add_get("/api/state", remote.get_state)
    app.router.add_get("/ws", remote.websocket)
    async def index(request):
        return web.FileResponse(STATIC / "index.html")
    app.router.add_get("/", index)
    app.router.add_static("/assets/", STATIC)
    return app
