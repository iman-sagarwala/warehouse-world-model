"""Local sandbox app: serves the viewer AND runs fixed-vs-MPC races on demand.

  python scripts/race_server.py     (or double-click run_race.bat)

Endpoints (same-origin for the served page):
  /                      the sandbox (rebuilt from template + latest data on every load)
  /ping                  -> ok            (the page uses this to detect the local app)
  /run?config=large-12-8[&seed=93][&fast=1]  -> {"job": id}   starts a race in a worker
  /status?job=id         -> {"state": "running"|"done"|"error", ...}
  /races.json            latest race library
"""
import io
import json
import os
import random
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8734
JOBS = {}
RUNNING = {}          # config -> job id, so double-fired requests join the same run


def build_html():
    tpl = io.open(os.path.join(ROOT, "results", "wwm_sandbox_template.html"), encoding="utf-8").read()
    data = io.open(os.path.join(ROOT, "results", "sim_data.json"), encoding="utf-8").read()
    rp = os.path.join(ROOT, "results", "races.json")
    races = io.open(rp, encoding="utf-8").read() if os.path.exists(rp) else "{}"
    return tpl.replace("__DATA__", data).replace("__RACES__", races)


def run_job(job, config, seed, fast, stress=False, stream=False):
    try:
        import multiprocessing as mp
        import record_race
        if fast:
            record_race.STEPS = 120          # plumbing smoke only
        with mp.Pool(2) as pool:
            res = pool.map(record_race.one, [(config, seed, "fixed", stress, stream), (config, seed, "mpc", stress, stream)])
        rp = os.path.join(ROOT, "results", "races.json")
        races = json.load(open(rp)) if os.path.exists(rp) else {}
        key = "%s@%d%s%s" % (config, seed, "s" if stress else "", "L" if stream else "")
        for cfg, sd, arm, arm_data, meta in res:
            if key not in races:
                races[key] = dict(config=cfg, seed=sd, stress=stress, stream=stream, **meta, arms={})
            races[key]["arms"][arm] = arm_data
        json.dump(races, open(rp, "w"), separators=(",", ":"), default=int)
        JOBS[job] = {"state": "done", "key": key}
    except Exception as e:                            # surfaced to the page, not swallowed
        JOBS[job] = {"state": "error", "message": str(e)[:300]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path in ("/", "/index.html"):
            body = build_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/world":
            wp = os.path.join(ROOT, "results", "wwm_world_template.html")
            body = io.open(wp, encoding="utf-8").read().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/ping":
            self._json({"ok": True})
        elif u.path == "/races.json":
            rp = os.path.join(ROOT, "results", "races.json")
            races = json.load(open(rp)) if os.path.exists(rp) else {}
            self._json(races)
        elif u.path == "/run":
            config = q.get("config", "large-8-6")
            seed = int(q.get("seed", random.randint(73, 144)))
            fast = q.get("fast") == "1"
            stress = q.get("stress") == "1"
            stream = q.get("stream") == "1"
            prev = RUNNING.get(config)
            if prev and JOBS.get(prev, {}).get("state") == "running":
                self._json({"job": prev, "config": config, "joined": True})
                return
            job = "j%d" % random.randint(10**8, 10**9)
            JOBS[job] = {"state": "running", "config": config, "seed": seed}
            RUNNING[config] = job
            threading.Thread(target=run_job, args=(job, config, seed, fast, stress, stream), daemon=True).start()
            self._json({"job": job, "config": config, "seed": seed})
        elif u.path == "/status":
            self._json(JOBS.get(q.get("job", ""), {"state": "unknown"}))
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv          # silent background mode (login autostart)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        if not quiet:
            print("sandbox app already running -- opening it")
            webbrowser.open("http://127.0.0.1:%d/" % PORT)
        sys.exit(0)
    url = "http://127.0.0.1:%d/" % PORT
    print("wwm_sim sandbox app:", url, "(Ctrl+C to stop)")
    if not quiet:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    srv.serve_forever()
