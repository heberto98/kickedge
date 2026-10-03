"""Run KickEdge locally: python -m kickedge.web [--open] (PORT/HOST env optional)."""
import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn


def kickedge_running(url):
    """True if a KickEdge health endpoint already answers at url."""
    try:
        with urllib.request.urlopen(url+'/healthz', timeout=2) as response:
            return json.loads(response.read()).get('status') == 'ok'
    except (OSError, ValueError):
        return False


def port_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
            return True
        except OSError:
            return False


def _open_when_ready(url):
    for _ in range(120):
        if kickedge_running(url):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m kickedge.web', description='Run KickEdge locally.')
    parser.add_argument('--open', action='store_true', help='open the browser when the server is ready')
    args = parser.parse_args(argv)
    host, port = os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8000'))
    url = f'http://{host}:{port}'
    if not port_free(host, port):
        if kickedge_running(url):
            print(f'KickEdge may already be running at {url}. Opening browser.')
            if args.open:
                webbrowser.open(url)
            return 0
        print(f'Port {port} is already used by another program. Close it, or start KickEdge on another '
              f'port, e.g. set PORT=8001.', file=sys.stderr)
        return 1
    if args.open:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    print(f'KickEdge: {url}  (press Ctrl+C to stop KickEdge)')
    uvicorn.run('kickedge.web.app:app', host=host, port=port, proxy_headers=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
