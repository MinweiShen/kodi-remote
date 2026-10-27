"""Deterministic preview backend; never opens uinput or controls real Kodi."""
import time

from .rpc import KodiError


class DemoKodi:
    connected = True

    def __init__(self, notify):
        self.notify = notify
        self.started = time.monotonic()
        self.base, self.paused, self.active = 24 * 60 + 15, False, True
        self.file = "/demo/星际旅人/Season 01/星际旅人 S01E02.mkv"
        self.volume, self.muted, self.subtitle = 65, False, True
        self.text = ""

    def position(self):
        return min(6120, self.base + (0 if self.paused else time.monotonic() - self.started))

    def set_time(self, value):
        self.base = max(0, min(6120, value))
        self.started = time.monotonic()

    async def call(self, method, **p):
        if method == "Player.GetActivePlayers":
            return [{"playerid": 1, "type": "video"}] if self.active else []
        if method == "Player.GetItem":
            return {"item": {"file": self.file, "label": self.file.rsplit("/", 1)[-1]}}
        if method == "Player.GetProperties":
            t = int(self.position())
            return {"time": {"hours": t // 3600, "minutes": t // 60 % 60, "seconds": t % 60},
                    "totaltime": {"hours": 1, "minutes": 42, "seconds": 0},
                    "speed": 0 if self.paused else 1, "canseek": True,
                    "subtitleenabled": self.subtitle,
                    "subtitles": [{"index": 0, "language": "chi", "name": "简体中文"}],
                    "audiostreams": [{"index": 0, "language": "chi", "name": "国语"},
                                     {"index": 1, "language": "eng", "name": "English"}],
                    "currentsubtitle": {"index": 0}, "currentaudiostream": {"index": 0}}
        if method == "Application.GetProperties":
            return {"volume": self.volume, "muted": self.muted}
        if method == "Player.PlayPause":
            self.set_time(self.position())
            self.paused = not self.paused
        elif method == "Player.Seek":
            value = p["value"]
            if "seconds" in value:
                self.set_time(self.position() + value["seconds"])
            else:
                t = value["time"]
                self.set_time(t.get("hours", 0) * 3600 + t.get("minutes", 0) * 60 + t.get("seconds", 0))
        elif method == "Player.Stop":
            self.active = False
        elif method == "Player.Open":
            self.active, self.paused = True, False
            self.file = p["item"]["file"]
            self.set_time(0)
        elif method == "Files.GetDirectory":
            return {"files": [{"file": f"/demo/星际旅人/Season 01/星际旅人 S01E{i:02}.mkv",
                                "filetype": "file"} for i in range(1, 5)]}
        elif method == "Application.SetVolume":
            self.volume = p["volume"]
        elif method == "Application.SetMute":
            self.muted = not self.muted
        elif method == "Player.SetSubtitle":
            self.subtitle = p["subtitle"] != "off"
        elif method == "Input.SendText":
            self.text = p["text"]
            self.notify("Input.OnInputFinished", {})
        elif method.startswith("Input."):
            if method == "Input.Select":
                self.notify("Input.OnInputRequested", {"type": "keyboard", "title": "演示搜索", "value": ""})
        elif method != "Player.SetAudioStream":
            raise KodiError("演示模式不支持该操作")
        return "OK"

    async def run(self):
        import asyncio
        await asyncio.Future()

    async def close(self):
        pass
