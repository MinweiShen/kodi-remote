"""Persistent, local Kodi JSON-RPC connection. Actions are never replayed."""
import asyncio
import contextlib
import itertools

import aiohttp


class KodiError(Exception):
    pass


class KodiRPC:
    def __init__(self, session, url, notify):
        self.session, self.url, self.notify = session, url, notify
        self.ws = None
        self.pending = {}
        self.ids = itertools.count(1)

    @property
    def connected(self):
        return self.ws is not None and not self.ws.closed

    async def run(self):
        while True:
            try:
                async with self.session.ws_connect(
                    self.url, heartbeat=15, timeout=5, max_msg_size=2**20
                ) as ws:
                    self.ws = ws
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        data = msg.json()
                        future = self.pending.get(data.get("id"))
                        if future is not None and not future.done():
                            if "error" in data:
                                future.set_exception(KodiError(data["error"].get("message", "Kodi 拒绝操作")))
                            else:
                                future.set_result(data.get("result"))
                        elif "method" in data:
                            self.notify(data["method"], data.get("params", {}).get("data", {}))
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            finally:
                self.ws = None
                self.notify("remote.disconnected", {})
                for future in list(self.pending.values()):
                    if not future.done():
                        future.set_exception(KodiError("Kodi 已断开；操作不会自动重发"))
            await asyncio.sleep(2)

    async def call(self, method, **params):
        if not self.connected:
            raise KodiError("Kodi 不可用，请检查本机远程控制设置")
        request_id = next(self.ids)
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.ws.send_json({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, 5)
        except (asyncio.TimeoutError, ConnectionError, RuntimeError) as exc:
            raise KodiError("Kodi 响应超时或连接中断；请核对电视，操作不会自动重发") from exc
        finally:
            self.pending.pop(request_id, None)

    async def close(self):
        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close()
