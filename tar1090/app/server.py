"""Private loopback HTTP API behind the ingress web server."""
import argparse
import http.server
import json
import signal
import threading
import urllib.parse
from pathlib import Path
from collector import Settings, State, collect, encode


def handler_for(state):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/config.js":
                body = ("SiteName = " + json.dumps(state.settings.site_name) + ";\n"
                        "PageName = SiteName; SiteShow = true;\n"
                        "MapType_tar1090 = " + json.dumps(state.settings.map_type) + ";\n"
                        "showPictures = false; planespottersAPI = false; planespottingAPI = false;\n"
                        "useRouteAPI = false; routeApiUrl = '';\n"
                        "enableMostWatchedFilter = false; enableActiveDates = false;\n"
                        "enableMostWatchedClickTracking = false; enableUAV = false;\n").encode()
                code, compressed, content_type = 200, False, "text/javascript"
            else:
                code, body, compressed = state.response(path)
                content_type = "application/json"
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if compressed:
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", default="/data/options.json")
    parser.add_argument("--port", type=int, default=8098)
    args = parser.parse_args()
    settings = Settings(json.loads(Path(args.options).read_text()))
    state, stop = State(settings), threading.Event()
    worker = threading.Thread(target=collect, args=(state, stop), daemon=True)
    worker.start()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(state))
    server.daemon_threads = True
    def shutdown(*_):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print("tar1090 collector API ready", flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker.join(settings.timeout_seconds * 2 + 1)


if __name__ == "__main__":
    main()
