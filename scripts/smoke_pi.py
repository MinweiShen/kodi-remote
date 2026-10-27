#!/usr/bin/env python3
"""Exercise the installed service against real Kodi and uinput, then restore state.

Run as pi with the input group: sudo -u pi /usr/bin/python3 scripts/smoke_pi.py
Uses temporary silent video fixtures. Never prints the service access key.
"""
import argparse
import asyncio
import contextlib
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import aiohttp
from evdev import InputDevice, ecodes, list_devices

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kodi_remote.rpc import KodiRPC


def timestamp(t):
    return t.get('hours', 0) * 3600 + t.get('minutes', 0) * 60 + t.get('seconds', 0)


async def until(function, predicate, timeout=12):
    async with asyncio.timeout(timeout):
        while True:
            value = await function()
            if predicate(value):
                return value
            await asyncio.sleep(.2)


async def main(mode='playback'):
    config = json.loads(Path('/etc/kodi-remote.json').read_text())
    origin = f"http://{config['host']}:{config['port']}"
    results = {}
    def passed(name, detail=True):
        results[name] = detail
        print('PASS', name, json.dumps(detail, ensure_ascii=False), flush=True)

    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        rpc = KodiRPC(session, config['kodi_url'], lambda *_: None)
        task = asyncio.create_task(rpc.run())
        ws = None
        keepalive = None
        device = None
        original = None
        cache = Path.home() / '.cache'
        cache.mkdir(exist_ok=True)
        fixture = tempfile.TemporaryDirectory(prefix='kodi-remote-smoke-', dir=cache)
        request_ids = itertools.count(1)
        async def state():
            async with session.get(origin + '/api/state') as response:
                response.raise_for_status()
                return await response.json()
        async def action(action, **params):
            current = await state()
            request_id = next(request_ids)
            await ws.send_json({'id': request_id, 'action': action,
                                'generation': current['generation'], **params})
            async with asyncio.timeout(12):
                while True:
                    reply = await ws.receive_json()
                    if reply.get('type') == 'result' and reply.get('id') == request_id:
                        if not reply.get('ok'):
                            raise RuntimeError(reply.get('error', 'Operation failed'))
                        return reply
        async def connect():
            socket = await session.ws_connect(origin.replace('http:', 'ws:') + '/ws', headers={'Origin': origin})
            first = await socket.receive_json()
            if not first.get('control'):
                await socket.close()
                raise RuntimeError('Another controller is active; close its page before running smoke tests')
            return socket
        async def player_properties():
            players = await rpc.call('Player.GetActivePlayers')
            video = next((p for p in players if p['type'] == 'video'), None)
            if not video:
                return {}
            return await rpc.call('Player.GetProperties', playerid=video['playerid'],
                                  properties=['time', 'totaltime', 'speed', 'canseek'])
        def events():
            with contextlib.suppress(BlockingIOError):
                return list(device.read())
            return []
        async def heartbeat():
            while True:
                await asyncio.sleep(4)
                if ws is not None and not ws.closed:
                    await ws.send_json({'action': 'heartbeat'})
        try:
            if mode != 'input':
                await until(lambda: asyncio.sleep(0, result=rpc.connected), bool)
                version = await rpc.call('Application.GetProperties', properties=['version', 'volume', 'muted'])
                players = await rpc.call('Player.GetActivePlayers')
                original = {'application': version, 'video': None}
                video = next((p for p in players if p['type'] == 'video'), None)
                if video:
                    original['video'] = {
                        'item': (await rpc.call('Player.GetItem', playerid=video['playerid'], properties=['file']))['item'],
                        'properties': await player_properties()}
                passed('kodi_version', version['version'])
            async with session.post(origin + '/api/login', headers={'Origin': origin},
                                    json={'secret': Path(config['secret_file']).read_text().strip()}) as response:
                assert response.status == 200, f'Login failed: {response.status}'
            current = await state()
            assert (mode == 'input' or current['online']) and not current['demo']
            passed('real_service_authenticated')
            ws = await connect()
            keepalive = asyncio.create_task(heartbeat())

            if mode == 'input':
                for path in list_devices():
                    candidate = InputDevice(path)
                    if candidate.name == 'Kodi Browser Remote':
                        device = candidate
                        break
                    candidate.close()
                assert device is not None, 'Virtual mouse not found'
                # Kodi GBM grabs mice exclusively. Run this mode while Kodi is stopped.
                device.grab()
                events()
                await action('preferences', sensitivity=3, acceleration=False)
                await action('move', samples=[[20, 10, 20]])
                emitted = events()
                assert any(e.type == ecodes.EV_REL and e.code == ecodes.REL_X and e.value == 60 for e in emitted)
                assert any(e.type == ecodes.EV_REL and e.code == ecodes.REL_Y and e.value == 30 for e in emitted)
                passed('uinput_relative_movement', {'dx': 60, 'dy': 30})
                await action('click', button='right')
                emitted = events()
                assert [e.value for e in emitted if e.type == ecodes.EV_KEY and e.code == ecodes.BTN_RIGHT] == [1, 0]
                await action('scroll', steps=2)
                assert any(e.code == ecodes.REL_WHEEL and e.value == 2 for e in events())
                await action('button', button='left', down=True)
                assert ecodes.BTN_LEFT in device.active_keys()
                await ws.close()
                await until(lambda: asyncio.sleep(0, result=device.active_keys()), lambda keys: ecodes.BTN_LEFT not in keys)
                passed('uinput_click_scroll_and_disconnect_release')
                print('RESULT', json.dumps({'ok': True, 'checks': len(results), 'results': results}, ensure_ascii=False), flush=True)
                return

            first = Path(fixture.name) / 'Control S01E01.mkv'
            second = Path(fixture.name) / 'Control S01E02.mkv'
            await asyncio.to_thread(subprocess.run, ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'color=c=black:s=64x64:r=1', '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono',
                            '-map', '0:v', '-map', '1:a', '-map', '1:a', '-t', '1500', '-c:v', 'mpeg4',
                            '-g', '1', '-q:v', '5', '-c:a', 'aac', '-b:a', '8k',
                            '-metadata:s:a:0', 'language=chi', '-metadata:s:a:1', 'language=eng', str(first)],
                           check=True, timeout=90, capture_output=True)
            shutil.copyfile(first, second)
            for video in (first, second):
                video.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:24:59,000\nKodi remote subtitle test\n')
            await rpc.call('Player.Open', item={'file': str(first)}, options={'resume': False})
            await until(state, lambda s: s.get('active') and s.get('duration', 0) >= 1400)
            await action('playpause')
            await until(state, lambda s: s.get('speed') == 0)
            await action('seek_to', seconds=750)
            await until(player_properties, lambda p: abs(timestamp(p.get('time', {})) - 750) <= 3)
            passed('play_pause_and_absolute_seek')
            expected = 750
            for delta in (-10, 10, -60, 60, -600, 600):
                await action('seek', seconds=delta)
                expected += delta
                actual = await until(player_properties, lambda p: abs(timestamp(p.get('time', {})) - expected) <= 3)
                passed(f'seek_{delta:+d}s', timestamp(actual['time']))
            await action('volume', delta=-5)
            volume = await rpc.call('Application.GetProperties', properties=['volume'])
            assert volume['volume'] == max(0, version['volume'] - 5)
            await action('mute')
            muted = await rpc.call('Application.GetProperties', properties=['muted'])
            assert muted['muted'] is not version['muted']
            passed('software_volume_and_mute')

            current = await until(state, lambda s: len(s.get('audio', [])) == 2 and len(s.get('subtitles', [])) > 0)
            await action('audio', index=current['audio'][1]['index'])
            await until(state, lambda s: s.get('audiostream') == current['audio'][1]['index'])
            await action('subtitle', index='off')
            await until(state, lambda s: not s.get('subtitleenabled'))
            await action('subtitle', index=current['subtitles'][0]['index'])
            await until(state, lambda s: s.get('subtitleenabled'))
            passed('audio_tracks_and_subtitles')

            await action('episode', direction=1)
            await until(state, lambda s: 'S01E02' in s.get('title', ''))
            await action('episode', direction=-1)
            await until(state, lambda s: 'S01E01' in s.get('title', ''))
            missing = await action('episode', direction=-1)
            assert not missing.get('choices') and '未找到' in missing.get('reason', '')
            passed('folder_previous_next_and_missing_episode')
            await action('stop')
            await until(state, lambda s: not s.get('active'))
            passed('stop_clears_playback_state')

            await rpc.call('GUI.ActivateWindow', window='videos', parameters=[fixture.name, 'return'])
            await asyncio.sleep(1)
            await rpc.call('Input.ExecuteAction', action='filter')
            current = await until(state, lambda s: s.get('input', {}).get('type') == 'keyboard' if s.get('input') else False)
            await action('text', text='流浪地球 2', input_id=current['input']['id'])
            await until(state, lambda s: s.get('input') is None)
            passed('unicode_text_dialog_submission', '流浪地球 2')
            print('RESULT', json.dumps({'ok': True, 'checks': len(results), 'results': results}, ensure_ascii=False), flush=True)
        finally:
            if keepalive:
                keepalive.cancel()
                await asyncio.gather(keepalive, return_exceptions=True)
            if device:
                with contextlib.suppress(OSError):
                    device.ungrab()
                device.close()
            if ws:
                await ws.close()
            if original:
                # Restore application settings and original playback, including paused state.
                await rpc.call('Application.SetVolume', volume=original['application']['volume'])
                await rpc.call('Application.SetMute', mute=original['application']['muted'])
                if original['video']:
                    old = original['video']
                    await rpc.call('Player.Open', item={'file': old['item']['file']}, options={'resume': False})
                    await until(player_properties, lambda p: bool(p.get('totaltime')))
                    player = next(p for p in await rpc.call('Player.GetActivePlayers') if p['type'] == 'video')
                    await rpc.call('Player.Seek', playerid=player['playerid'], value={'time': old['properties']['time']})
                    await rpc.call('Player.PlayPause', playerid=player['playerid'], play=old['properties']['speed'] != 0)
                else:
                    for player in await rpc.call('Player.GetActivePlayers'):
                        if player['type'] == 'video':
                            await rpc.call('Player.Stop', playerid=player['playerid'])
                    await rpc.call('Input.Back')
                    await rpc.call('Input.Home')
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await rpc.close()
            fixture.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['input', 'playback'], default='playback')
    asyncio.run(main(parser.parse_args().mode))
