"""A stand-in for one marlin-drone coordinator (:7070), for testing scripts/ without SITL.

Shapes follow marlin-drone 7760d04 (coordinator 1.8.4), drone/drone_api_server.py:
- POST /api/takeoff and /api/land answer {"task_id", "message"} on 200 and
  {"detail": ...} on 409/504; bodies are extra="forbid".
- POST /api/set-mode answers {"status": "success", "mode", "result": "ACCEPTED", ...}.
- GET /tasks/{id} answers the task_registry record ({"task_id", "state", ...}).
- /get_drone_state: `update_time` is seconds, `timestamp` is milliseconds (G2).

The flight model is deliberately crude: after a takeoff alt_rel climbs at `climb_rate`
m/s up to the commanded altitude; after a land the aircraft disarms `land_s` later.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GUIDED, QLAND, QRTL = 15, 20, 21


class FakeDrone:
    def __init__(
        self,
        *,
        flight_mode=QRTL,
        is_armed=False,
        ready_after_guided=True,
        takeoff_status=200,
        takeoff_detail="",
        climb_rate=40.0,
        land_s=0.3,
        takeoff_delay=0.0,
    ):
        self.flight_mode = flight_mode
        self.is_armed = is_armed
        self.ready_after_guided = ready_after_guided
        self.takeoff_status = takeoff_status
        self.takeoff_detail = takeoff_detail
        self.climb_rate = climb_rate
        self.land_s = land_s
        # Seconds the takeoff request takes before the aircraft arms and the 200 goes out,
        # like a flight controller slow to acknowledge GUIDED + ARM + NAV_TAKEOFF.
        self.takeoff_delay = takeoff_delay

        self.requests: list[tuple[str, str, object]] = []  # (method, path, json body)
        self.tasks: dict[str, dict] = {}
        self._takeoff_at: float | None = None
        self._takeoff_alt = 10.0
        self._land_at: float | None = None
        self._n = 0
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    # ---- flight model ------------------------------------------------------------
    def state(self) -> dict:
        now = time.time()
        with self._lock:
            alt = 0.0
            if self._takeoff_at is not None:
                alt = min(self._takeoff_alt, (now - self._takeoff_at) * self.climb_rate)
            if self._land_at is not None and now - self._land_at >= self.land_s:
                self.is_armed = False
                self._takeoff_at = None
                self._land_at = None
                alt = 0.0
            ready = self.flight_mode == GUIDED and self.ready_after_guided
            return {
                "cur_task_id": None,
                "lat": 25.0235515,
                "lng": 121.4872371,
                "alt_rel": round(alt, 2),
                "alt_asl": round(alt + 7.4, 2),
                "battery_voltage": 23.96,
                "update_time": int(now),
                "flight_mode": self.flight_mode,
                "is_armed": self.is_armed,
                "is_ready_to_arm": ready or self.is_armed,
                "gps_fix_type": 6,
                "satellites_visible": 10,
                "timestamp": int(now * 1000),
            }

    def _new_task(self, kind: str) -> str:
        self._n += 1
        task_id = f"fake{self._n:04d}"
        self.tasks[task_id] = {"task_id": task_id, "state": "running", "kind": kind, "detail": ""}
        return task_id

    # ---- HTTP --------------------------------------------------------------------
    def handle(self, method: str, path: str, body):
        self.requests.append((method, path, body))
        if method == "GET" and path == "/version":
            return 200, {"version": "1.8.4"}
        if method == "GET" and path == "/get_drone_state":
            return 200, self.state()
        if method == "GET" and path.startswith("/tasks/"):
            record = self.tasks.get(path.removeprefix("/tasks/"))
            if record is None:
                return 404, {"detail": "No record"}
            return 200, record
        if method == "POST" and path == "/api/set-mode":
            with self._lock:
                self.flight_mode = {"GUIDED": GUIDED, "QLAND": QLAND, "QRTL": QRTL}[body["mode"]]
            return 200, {"status": "success", "mode": body["mode"], "result": "ACCEPTED",
                         "superseded_task_id": None}
        if method == "POST" and path == "/api/takeoff":
            if self.takeoff_status != 200:
                return self.takeoff_status, {"detail": self.takeoff_detail}
            time.sleep(self.takeoff_delay)
            with self._lock:
                self.flight_mode = GUIDED
                self.is_armed = True
                self._land_at = None  # this takeoff lands after any land that came first
                self._takeoff_at = time.time()
                self._takeoff_alt = float(body.get("altitude", 10.0))
                task_id = self._new_task("TAKE_OFF")
            return 200, {"task_id": task_id, "message": "TAKEOFF accepted"}
        if method == "POST" and path == "/api/land":
            with self._lock:
                self.flight_mode = QLAND
                self._land_at = time.time()
                for record in self.tasks.values():
                    if record["state"] == "running":
                        record["state"] = "superseded"
                task_id = self._new_task("LAND")
                self.tasks[task_id]["state"] = "succeeded"
            return 200, {"task_id": task_id, "message": "LAND accepted"}
        return 404, {"detail": "Not Found"}

    def posts(self) -> list[tuple[str, object]]:
        return [(p, b) for m, p, b in self.requests if m == "POST"]

    def __enter__(self) -> str:
        drone = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, method):
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                status, payload = drone.handle(method, self.path, body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._reply("GET")

            def do_POST(self):
                self._reply("POST")

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __exit__(self, *exc):
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
