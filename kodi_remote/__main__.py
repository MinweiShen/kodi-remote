import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from .server import create_app


def main():
    parser = argparse.ArgumentParser(description="iPhone browser remote for Kodi")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--demo", action="store_true", help="loopback-only preview with simulated Kodi and mouse")
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else {}
    config.setdefault("host", "127.0.0.1")
    config.setdefault("port", 8091)
    config.setdefault("kodi_url", "ws://127.0.0.1:9090/jsonrpc")
    if args.host:
        config["host"] = args.host
    if args.port:
        config["port"] = args.port
    config["demo"] = args.demo
    if args.demo:
        if config["host"] not in ("127.0.0.1", "::1", "localhost"):
            parser.error("演示模式只允许监听本机回环地址")
        config["secret"] = "demo"
    else:
        secret_file = Path(config.get("secret_file", "/etc/kodi-remote.secret"))
        if secret_file.stat().st_mode & 0o007:
            parser.error("访问密钥不能允许其他用户读取；建议 root:pi 0640")
        config["secret"] = secret_file.read_text().strip()
        minimum_length = 4 if config.get("allow_short_secret") is True else 24
        if len(config["secret"]) < minimum_length:
            parser.error(f"访问密钥至少需要 {minimum_length} 个字符")
        target = urlsplit(config["kodi_url"])
        if target.scheme != "ws" or target.hostname not in ("127.0.0.1", "::1", "localhost"):
            parser.error("Kodi 必须使用本机回环 WebSocket 地址")
    print(f"Kodi remote: http://{config['host']}:{config['port']}/" + (" (演示模式，密钥 demo)" if args.demo else ""), flush=True)
    web.run_app(create_app(config), host=config["host"], port=config["port"], access_log=None,
                print=None)


if __name__ == "__main__":
    main()
