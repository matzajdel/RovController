#!/usr/bin/env python3
"""
OPS Control Panel - Web page to start/stop frontend & backend as subprocesses.
Stdout/stderr is captured to log files and streamed live to the browser.
Runs on port 1337.
"""

import subprocess
import http.server
import json
import os
import signal
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

BACKEND_LOG = os.path.join(LOG_DIR, "backend.log")
FRONTEND_LOG = os.path.join(LOG_DIR, "frontend.log")

SERVICES = {
    "backend": {
        "cmd": ["bash", "start_backend.sh"],
        "cwd": os.path.join(PROJECT_DIR, "backend"),
        "log": BACKEND_LOG,
        "proc": None,          # Popen object
        "pid": None,
    },
    "frontend": {
        "cmd": ["bash", "start_frontend.sh"],
        "cwd": os.path.join(PROJECT_DIR, "frontend"),
        "log": FRONTEND_LOG,
        "proc": None,
        "pid": None,
    },
}

# ── Internal event log (shown on the page) ──────────────────────────
EVENT_LOG = []
MAX_EVENTS = 300


def log_event(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    EVENT_LOG.append({"ts": ts, "msg": msg})
    if len(EVENT_LOG) > MAX_EVENTS:
        EVENT_LOG.pop(0)
    print(f"[{ts}] {msg}", flush=True)


# ── Process helpers ──────────────────────────────────────────────────
def _pipe_reader(pipe, logfile_handle, label):
    """Read lines from a pipe and write to log file (runs in a thread)."""
    try:
        for line in iter(pipe.readline, ""):
            logfile_handle.write(line)
            logfile_handle.flush()
        pipe.close()
    except Exception as e:
        log_event(f"{label} pipe reader error: {e}")


def is_running(name: str) -> bool:
    svc = SERVICES[name]
    proc = svc["proc"]
    if proc is None:
        return False
    ret = proc.poll()
    if ret is not None:
        log_event(f"{name} process exited with code {ret}")
        svc["proc"] = None
        svc["pid"] = None
        return False
    return True


def start_service(name: str) -> dict:
    svc = SERVICES[name]

    if is_running(name):
        log_event(f"START {name} → already running (pid {svc['pid']})")
        return {"ok": False, "reason": "already running", "pid": svc["pid"]}

    # Prepare log file
    logf = open(svc["log"], "w")
    logf.write(f"--- {name} started at {datetime.now().isoformat()} ---\n")
    logf.write(f"--- cmd: {' '.join(svc['cmd'])} ---\n")
    logf.write(f"--- cwd: {svc['cwd']} ---\n\n")
    logf.flush()

    log_event(f"START {name} → spawning: {' '.join(svc['cmd'])} (cwd={svc['cwd']})")

    try:
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=svc["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,                 # line-buffered
            preexec_fn=os.setsid,      # new process group for clean kill
        )
    except Exception as e:
        log_event(f"START {name} → FAILED: {e}")
        logf.write(f"\n!!! FAILED TO START: {e}\n")
        logf.close()
        return {"ok": False, "reason": str(e)}

    svc["proc"] = proc
    svc["pid"] = proc.pid

    # Background thread to pipe stdout → log file
    t = threading.Thread(
        target=_pipe_reader,
        args=(proc.stdout, logf, name),
        daemon=True,
    )
    t.start()

    log_event(f"START {name} → pid {proc.pid}")
    return {"ok": True, "pid": proc.pid}


def stop_service(name: str) -> dict:
    svc = SERVICES[name]

    if not is_running(name):
        log_event(f"STOP {name} → not running")
        return {"ok": False, "reason": "not running"}

    proc = svc["proc"]
    pid = svc["pid"]
    log_event(f"STOP {name} → sending SIGTERM to process group (pid {pid})")

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass

    # Wait up to 5s for graceful shutdown
    try:
        proc.wait(timeout=5)
        log_event(f"STOP {name} → exited (code {proc.returncode})")
    except subprocess.TimeoutExpired:
        log_event(f"STOP {name} → SIGTERM timeout, sending SIGKILL")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=3)
        except Exception:
            pass
        log_event(f"STOP {name} → killed")

    svc["proc"] = None
    svc["pid"] = None
    return {"ok": True}


def read_log_tail(logfile: str, lines: int = 100) -> str:
    try:
        with open(logfile, "rb") as f:
            try:
                f.seek(-65536, 2)
            except OSError:
                f.seek(0)
            data = f.read().decode("utf-8", errors="replace")
        return "\n".join(data.splitlines()[-lines:])
    except FileNotFoundError:
        return "(no log file yet — start the service first)"


# ── HTML ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OPS Control Panel</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Courier New', monospace; background: #0d1117; color: #c9d1d9; }
  .top { display: flex; gap: 20px; padding: 20px; flex-wrap: wrap; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 10px;
          padding: 20px; flex: 1; min-width: 320px; }
  h1 { color: #e94560; font-size: 1.3em; margin-bottom: 16px; text-align: center; }
  h2 { color: #58a6ff; font-size: 1em; margin-bottom: 10px; }

  .svc { display: flex; align-items: center; justify-content: space-between;
         padding: 12px 16px; margin-bottom: 10px; background: #0d1117;
         border: 1px solid #30363d; border-radius: 8px; }
  .svc-left { display: flex; align-items: center; gap: 10px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .dot.on  { background: #3fb950; box-shadow: 0 0 8px #3fb950; }
  .dot.off { background: #484f58; }
  .svc-name { font-weight: bold; font-size: 1.05em; }
  .svc-status { color: #8b949e; font-size: .85em; }

  .btns { display: flex; gap: 6px; }
  button { padding: 7px 16px; border: none; border-radius: 6px; cursor: pointer;
           font-family: inherit; font-size: .9em; font-weight: bold; transition: .15s; }
  .b-start { background: #238636; color: #fff; }
  .b-start:hover { background: #2ea043; }
  .b-stop  { background: #da3633; color: #fff; }
  .b-stop:hover  { background: #f85149; }
  .b-all { width: 100%; padding: 10px; margin-top: 4px; }

  .logs-area { display: flex; gap: 20px; padding: 0 20px 20px; flex-wrap: wrap; }
  .log-box { flex: 1; min-width: 320px; }
  .log-header { display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 6px; }
  .log-header h2 { margin: 0; }
  .log-tab { display: flex; gap: 4px; }
  .log-tab button { padding: 4px 10px; font-size: .8em; background: #21262d;
                    color: #8b949e; border: 1px solid #30363d; }
  .log-tab button.active { background: #30363d; color: #c9d1d9; }
  pre { background: #010409; border: 1px solid #30363d; border-radius: 8px;
        padding: 12px; height: 340px; overflow-y: auto; font-size: .82em;
        line-height: 1.45; white-space: pre-wrap; word-break: break-all;
        color: #adbac7; }
  pre .ts { color: #568af2; }
  pre .err { color: #f47067; }
  pre .ok  { color: #57ab5a; }

  .event-section { padding: 0 20px 20px; }
  .event-pre { height: 180px; }
</style>
</head>
<body>

<div class="top">
  <div class="card">
    <h1>⚙ OPS Control Panel</h1>

    <div class="svc">
      <div class="svc-left">
        <span class="dot off" id="dot-backend"></span>
        <span class="svc-name">Backend</span>
        <span class="svc-status" id="lbl-backend">—</span>
      </div>
      <div class="btns">
        <button class="b-start" onclick="act('start','backend')">Start</button>
        <button class="b-stop"  onclick="act('stop','backend')">Stop</button>
      </div>
    </div>

    <div class="svc">
      <div class="svc-left">
        <span class="dot off" id="dot-frontend"></span>
        <span class="svc-name">Frontend</span>
        <span class="svc-status" id="lbl-frontend">—</span>
      </div>
      <div class="btns">
        <button class="b-start" onclick="act('start','frontend')">Start</button>
        <button class="b-stop"  onclick="act('stop','frontend')">Stop</button>
      </div>
    </div>

    <button class="b-start b-all" onclick="act('start','all')">▶ Start All</button>
    <button class="b-stop b-all"  onclick="act('stop','all')">■ Stop All</button>
  </div>
</div>

<div class="logs-area">
  <div class="log-box">
    <div class="log-header">
      <h2>Backend Log</h2>
      <span class="svc-status" id="log-ts-backend">—</span>
    </div>
    <pre id="log-backend">(waiting...)</pre>
  </div>
  <div class="log-box">
    <div class="log-header">
      <h2>Frontend Log</h2>
      <span class="svc-status" id="log-ts-frontend">—</span>
    </div>
    <pre id="log-frontend">(waiting...)</pre>
  </div>
</div>

<div class="event-section">
  <h2>Control Panel Events</h2>
  <pre class="event-pre" id="events">(waiting...)</pre>
</div>

<script>
function act(action, svc) {
  fetch('/api/' + action + '/' + svc, {method:'POST'})
    .then(r => r.json())
    .then(d => {
      console.log(action, svc, d);
      refresh();
    });
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function colorize(text) {
  return esc(text)
    .replace(/^(.*error.*|.*Error.*|.*ERR.*|.*FAIL.*|.*Traceback.*)$/gim, '<span class="err">$1</span>')
    .replace(/^(.*started.*|.*listening.*|.*ready.*|.*Running.*)$/gim, '<span class="ok">$1</span>');
}

function refresh() {
  fetch('/api/status').then(r=>r.json()).then(d => {
    ['backend','frontend'].forEach(s => {
      const on = d[s];
      const pid = d[s+'_pid'];
      document.getElementById('dot-'+s).className = 'dot '+(on?'on':'off');
      document.getElementById('lbl-'+s).textContent = on ? 'RUNNING (pid '+pid+')' : 'STOPPED';
    });
  });

  ['backend','frontend'].forEach(s => {
    fetch('/api/logs/'+s).then(r=>r.json()).then(d => {
      const el = document.getElementById('log-'+s);
      el.innerHTML = colorize(d.log);
      el.scrollTop = el.scrollHeight;
      document.getElementById('log-ts-'+s).textContent = 'updated: ' + new Date().toLocaleTimeString();
    });
  });

  fetch('/api/events').then(r=>r.json()).then(d => {
    const el = document.getElementById('events');
    el.innerHTML = d.events.map(e =>
      '<span class="ts">['+e.ts+']</span> ' + esc(e.msg)
    ).join('\n');
    el.scrollTop = el.scrollHeight;
  });
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


# ── HTTP Handler ─────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self._json({
                "backend": is_running("backend"),
                "frontend": is_running("frontend"),
                "backend_pid": SERVICES["backend"]["pid"],
                "frontend_pid": SERVICES["frontend"]["pid"],
            })
        elif path == "/api/logs/backend":
            self._json({"log": read_log_tail(BACKEND_LOG)})
        elif path == "/api/logs/frontend":
            self._json({"log": read_log_tail(FRONTEND_LOG)})
        elif path == "/api/events":
            self._json({"events": EVENT_LOG[-100:]})
        else:
            self._html(HTML)

    def do_POST(self):
        parts = self.path.strip("/").split("/")  # api/<action>/<service>
        if len(parts) != 3 or parts[0] != "api":
            self._json({"error": "bad request"}, 400)
            return

        action, service = parts[1], parts[2]
        results = {}

        targets = []
        if service in ("backend", "all"):
            targets.append("backend")
        if service in ("frontend", "all"):
            targets.append("frontend")

        if not targets:
            self._json({"error": f"unknown service: {service}"}, 400)
            return

        for name in targets:
            if action == "start":
                results[name] = start_service(name)
            elif action == "stop":
                results[name] = stop_service(name)
            else:
                self._json({"error": f"unknown action: {action}"}, 400)
                return

        self._json(results)

    # ── Response helpers ──────────────────────────────────
    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress default HTTP logs, we have our own


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = 1337
    log_event("Control Panel starting up")
    log_event(f"Project dir: {PROJECT_DIR}")
    log_event(f"Log dir: {LOG_DIR}")
    for name, svc in SERVICES.items():
        log_event(f"  {name}: {' '.join(svc['cmd'])} (cwd={svc['cwd']})")

    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    log_event(f"Listening on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_event("Shutting down — killing child processes")
        for name in SERVICES:
            if is_running(name):
                stop_service(name)
        server.server_close()
        log_event("Bye")
