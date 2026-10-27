import asyncio
import tempfile
import unittest
from pathlib import Path

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from kodi_remote.episodes import identify, neighbors, playable, local_videos
from kodi_remote.mouse import Mouse
from kodi_remote.rpc import KodiError, KodiRPC
from kodi_remote.server import create_app


class EpisodesTests(unittest.TestCase):
    def test_numeric_order_and_missing_episode(self):
        files = [f"/show/{i}.mkv" for i in (1, 2, 9, 10)]
        self.assertEqual(neighbors(files[2], files, 1)[0], "/show/10.mkv")
        self.assertEqual(neighbors(files[1], files, 1)[1], [])

    def test_same_show_and_season_only(self):
        current = "/show/My Show S01E09.mkv"
        target = "/show/My Show S01E10.mkv"
        files = [current, target, "/show/Other Show S01E10.mkv", "/show/My Show S02E10.mkv"]
        self.assertEqual(neighbors(current, files, 1)[0], target)

    def test_duplicates_and_unknown_names_require_choice(self):
        current = "/show/Show S01E01.mkv"
        files = [current, "/show/Show S01E02 [1080p].mkv", "/show/Show S01E02 [720p].mkv"]
        target, choices, reason = neighbors(current, files, 1)
        self.assertIsNone(target)
        self.assertEqual(len(choices), 2)
        self.assertIn("多个版本", reason)
        self.assertIsNone(identify("Film 2026 1080p.mkv"))
        self.assertIsNone(identify("Show S01E01-E03.mkv"))

    def test_chinese_and_fansub_names(self):
        self.assertEqual(identify("动漫 第09集.mkv"), ("动漫", None, 9))
        self.assertEqual(identify("[Group] Show - 02 [1080p].mkv"), ("show", None, 2))
        self.assertEqual(identify("Show EP02.mkv"), ("show", None, 2))
        self.assertEqual(identify("Show_S01E02.mkv"), ("show", 1, 2))

    def test_extras_and_partial_downloads(self):
        self.assertFalse(playable("Show NCOP.mkv"))
        self.assertFalse(playable("Show E02.mkv.part"))
        self.assertFalse(playable("Show E02.srt"))

    def test_local_folder_does_not_need_kodi_source_and_excludes_symlink_escape(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            root = Path(folder)
            current = root / '动漫 S01E01.mkv'
            target = root / '动漫 S01E02.mkv'
            current.touch(); target.touch()
            (root / '动漫 S01E03.mkv.part').touch()
            (root / 'nested').mkdir()
            foreign = Path(outside) / '动漫 S01E03.mkv'
            foreign.touch()
            (root / '动漫 S01E03.mkv').symlink_to(foreign)
            files = local_videos(root)
            self.assertEqual(set(files), {str(current.resolve()), str(target.resolve())})
            self.assertEqual(neighbors(str(current.resolve()), files, 1)[0], str(target.resolve()))


class MouseTests(unittest.TestCase):
    def test_small_movements_preserve_fractional_distance(self):
        mouse = Mouse(demo=True)
        output = [mouse.move(.1, 0, 16, sensitivity=1, acceleration=False)[0] for _ in range(100)]
        self.assertAlmostEqual(sum(output) + mouse.remainder[0], 10)

    def test_fast_swipe_has_more_gain(self):
        slow, fast = Mouse(True), Mouse(True)
        a = sum(slow.move(2, 0, 20)[0] for _ in range(20))
        b = sum(fast.move(2, 0, 1)[0] for _ in range(20))
        self.assertGreater(b, a * 1.5)

    def test_release_clears_drag(self):
        mouse = Mouse(True)
        mouse.button("left", True)
        mouse.release()
        self.assertEqual(mouse.pressed, set())


class RemoteIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app({"secret": "test-secret", "demo": True})
        self.client = TestClient(TestServer(self.app), cookie_jar=aiohttp.CookieJar(unsafe=True))
        await self.client.start_server()
        self.origin = str(self.client.make_url('/')).rstrip('/')
        self.headers = {"Origin": self.origin}
        response = await self.client.post('/api/login', json={"secret": "test-secret"}, headers=self.headers)
        self.assertEqual(response.status, 200)
        for _ in range(50):
            if self.app.remote.state.get('active'):
                break
            await asyncio.sleep(.01)

    async def asyncTearDown(self):
        await self.client.close()

    async def ws(self):
        ws = await self.client.ws_connect('/ws', headers=self.headers)
        await ws.receive_json()
        return ws

    async def action(self, ws, action, **data):
        await ws.send_json({"id": 7, "action": action, "generation": self.app.remote.state['generation'], **data})
        while True:
            result = await ws.receive_json()
            if result.get('type') == 'result' and result.get('id') == 7:
                return result

    async def test_auth_and_cross_origin_rejected(self):
        response = await self.client.post('/api/login', json={"secret":"test-secret"}, headers={"Origin":"http://evil.test"})
        self.assertEqual(response.status, 403)
        with self.assertRaises(aiohttp.WSServerHandshakeError):
            await self.client.ws_connect('/ws', headers={"Origin":"http://evil.test"})
        other = TestClient(TestServer(create_app({"secret":"secret", "demo":True})))
        await other.start_server()
        try:
            response = await other.get('/api/state')
            self.assertEqual(response.status, 401)
        finally:
            await other.close()

    async def test_takeover_and_disconnect_release_mouse(self):
        a = await self.ws()
        result = await self.action(a, 'button', button='left', down=True)
        self.assertTrue(result['ok'])
        self.assertEqual(self.app.remote.mouse.pressed, {'left'})
        b = await self.ws()
        self.assertFalse((await self.action(b,'click'))['ok'])
        self.assertTrue((await self.action(b,'takeover'))['ok'])
        self.assertEqual(self.app.remote.mouse.pressed,set())
        self.assertFalse((await self.action(a,'button',button='left',down=True))['ok'])
        await self.action(b,'button',button='left',down=True)
        await b.close()
        for _ in range(50):
            if not self.app.remote.mouse.pressed: break
            await asyncio.sleep(.01)
        self.assertEqual(self.app.remote.mouse.pressed,set())

    async def test_seek_validation_and_stale_media(self):
        ws = await self.ws()
        self.assertTrue((await self.action(ws,'seek',seconds=60))['ok'])
        self.assertFalse((await self.action(ws,'seek',seconds=999999))['ok'])
        self.assertFalse((await self.action(ws,'seek',seconds=60,generation=-1))['ok'])
        self.assertFalse((await self.action(ws,'System.Reboot'))['ok'])
        self.assertFalse((await self.action(ws,'move',samples=[[float('nan'),0,16]]))['ok'])

    async def test_chinese_requires_input_target(self):
        ws = await self.ws()
        self.assertFalse((await self.action(ws,'text',text='流浪地球 2'))['ok'])
        await self.action(ws,'nav',key='select')
        self.assertFalse((await self.action(ws,'text',text='流浪地球 2',input_id='stale-dialog'))['ok'])
        self.assertTrue((await self.action(ws,'text',text='流浪地球 2',input_id=self.app.remote.input_target['id']))['ok'])
        self.assertEqual(self.app.remote.rpc.text,'流浪地球 2')

    async def test_next_episode_needs_no_playlist(self):
        ws = await self.ws()
        self.assertTrue((await self.action(ws,'episode',direction=1))['ok'])
        self.assertTrue(self.app.remote.rpc.file.endswith('S01E03.mkv'))
        self.assertFalse((await self.action(ws,'choose_episode',choice='/etc/passwd'))['ok'])

    async def test_takeover_cancels_unsent_inflight_command(self):
        a, b = await self.ws(), await self.ws()
        reached = asyncio.Event()
        original = self.app.remote.rpc.call
        async def slow(method, **params):
            if method == 'Player.GetItem':
                reached.set()
                await asyncio.sleep(30)
            return await original(method, **params)
        self.app.remote.rpc.call = slow
        await a.send_json({'id':9,'action':'seek','seconds':60,'generation':self.app.remote.state['generation']})
        await asyncio.wait_for(reached.wait(),1)
        self.assertTrue((await self.action(b,'takeover'))['ok'])
        while True:
            message=await asyncio.wait_for(a.receive_json(),1)
            if message.get('type')=='result' and message.get('id')==9:
                self.assertFalse(message['ok'])
                break


class RPCIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_response_notification_and_no_replay_after_disconnect(self):
        notifications, requests = [], []
        async def kodi(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for msg in ws:
                data=msg.json();requests.append(data)
                if data['method']=='Player.Seek':
                    await ws.close()
                    break
                await ws.send_json({'jsonrpc':'2.0','id':data['id'],'result':{'pong':True}})
                await ws.send_json({'jsonrpc':'2.0','method':'Input.OnInputRequested','params':{'data':{'type':'keyboard'}}})
            return ws
        app=web.Application();app.router.add_get('/jsonrpc',kodi)
        server=TestServer(app);await server.start_server()
        async with aiohttp.ClientSession() as session:
            rpc=KodiRPC(session,str(server.make_url('/jsonrpc')).replace('http:','ws:'),lambda method,data: notifications.append(method))
            task=asyncio.create_task(rpc.run())
            try:
                for _ in range(100):
                    if rpc.connected:break
                    await asyncio.sleep(.01)
                self.assertEqual(await rpc.call('JSONRPC.Ping'),{'pong':True})
                with self.assertRaises(KodiError):await rpc.call('Player.Seek',playerid=1,value={'seconds':60})
                self.assertEqual(len(requests),2)
                self.assertIn('Input.OnInputRequested',notifications)
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True);await rpc.close()
        await server.close()


if __name__ == '__main__':
    unittest.main()
