"""Minimal log tailer — zero dependencies (stdlib only).

Serves an HTML dashboard + SSE stream of all logs/*.log files.
Usage:  python scripts/logtail.py [--port 8001] [--dir logs]
"""
import argparse
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread

HTML = b"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Eon Logs</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font:13px/1.5 monospace;padding:16px}
h1{font-size:16px;margin-bottom:8px;color:#58a6ff}
select{background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:4px;padding:4px 8px;margin-bottom:12px}
#logs{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px;height:calc(100vh - 80px);overflow-y:auto}
.l{padding:1px 0;border-bottom:1px solid #21262d;white-space:pre-wrap;word-break:break-all}
.l .ts{color:#484f58}.l .lv{width:55px;display:inline-block}.l .INFO{color:#3fb950}.l .WARNING{color:#d29922}.l .ERROR{color:#f85149}.l .DEBUG{color:#8b949e}
</style></head><body>
<h1>Eon Logs</h1>
<select id="f" onchange="filter()"><option value="">all files</option></select>
<div id="logs"></div>
<script>
var C=200,E=[],F="",S=new EventSource("/stream");
var L=document.getElementById("logs"),F2=document.getElementById("f");
S.onmessage=function(e){var d=JSON.parse(e.data);
if(F&&d.f!==F)return;E.push(d);if(E.length>C)E=E.slice(-C);render()};
function filter(){F=F2.value;E=[];render()}
function render(){L.innerHTML=E.map(function(e){
var m=e.m.replace(/</g,"&lt;");return'<div class="l"><span class="ts">'+e.t+'</span> <span class="lv '+e.l+'">'+e.l+'</span> '+m+'</div>'}).join("");L.scrollTop=L.scrollHeight}
S.onerror=function(){setTimeout(function(){S.close();S=new EventSource("/stream")},2000)};
</script></body></html>"""


class Tailer:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.offsets: dict[str, int] = {}

    def poll(self):
        results = []
        for fp in self.log_dir.glob("*.log"):
            name = fp.name
            if name not in self.offsets:
                self.offsets[name] = fp.stat().st_size
                continue
            try:
                size = fp.stat().st_size
                if size < self.offsets[name]:
                    self.offsets[name] = 0
                if size == self.offsets[name]:
                    continue
                with open(fp, "r", errors="replace") as f:
                    f.seek(self.offsets[name])
                    data = f.read()
                    self.offsets[name] = f.tell()
                for line in data.splitlines():
                    if not line.strip():
                        continue
                    try:
                        doc = json.loads(line)
                        results.append({
                            "t": doc.get("timestamp", "")[:19],
                            "l": doc.get("level", "INFO"),
                            "m": doc.get("message", line),
                            "f": name,
                        })
                    except json.JSONDecodeError:
                        results.append({"t": "", "l": "INFO", "m": line, "f": name})
            except OSError:
                pass
        return results


class Handler(BaseHTTPRequestHandler):
    log_dir: Path = Path("logs")  # set by main

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML)
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            tailer = Tailer(self.log_dir)
            try:
                while True:
                    for ev in tailer.poll():
                        self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                        self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def log_message(self, *_):
        pass


def main():
    ap = argparse.ArgumentParser(description="Eon log tailer")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--dir", type=str, default="logs")
    args = ap.parse_args()

    log_dir = Path(args.dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    Handler.log_dir = log_dir

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Log tailer on http://localhost:{args.port}  (watching {log_dir}/)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
