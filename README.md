# marine-backend-py

A minimal FastAPI backend for drone-container developers to test their work by hand.
It sits between the browser ([marine-frontend](../marine-frontend)) and each drone's
marlin-drone coordinator HTTP API (:7070). It is not a production GCS.

```
browser (marine-frontend) ──► marine-backend-py :8100 ──► drone-N coordinator :7070 ──► ArduPlane SITL
```

The plan, decisions and workflow rules are in [ROADMAP.md](ROADMAP.md); measured numbers
and pitfalls are in [docs/baseline.md](docs/baseline.md).

## Quick start

```bash
uv sync             # installs Python 3.12 and the locked dependencies
uv run pytest       # unit tests, no SITL needed
scripts/dev.sh      # serves on http://localhost:8100
curl localhost:8100/health   # {"ok":true}
```

To characterise a drone directly (flies it: 3 takeoffs to 10 m and 3 landings):

```bash
scripts/baseline_drone_direct.sh http://172.18.10.2:7070
```

## Progress

| Step | What | Status |
|---|---|---|
| 1 | Skeleton + drone API baseline | Done on branch `step-1-skeleton`: `/health`, tests, scripts, baseline measured on drone-1 SITL |
| 2 | `GET /api/drones`: drone list + live state | Not started |
| 3 | takeoff / land / task forwarding | Not started |

What is verified today:

- `GET /health` returns `{"ok":true}` (unit test, and `scripts/smoke_health.sh` against a real uvicorn).
- The drone's own API, measured directly on drone-1 SITL (coordinator 1.8.4, ArduPlane 4.6.3):
  median takeoff to 9.5 m in 5.28 s, median land-to-disarm in 22.97 s over 3 runs.

What does **not** exist yet: no endpoint talks to a drone. The backend cannot show drone
state or command a takeoff; that is steps 2 and 3.

## Known pitfalls

- `is_ready_to_arm` is always false in QLAND, QRTL and RTL (ArduPlane "mode not
  armable"), including right after a landing. It does not mean a takeoff will fail.
- If your shell sources ROS Humble, its `PYTHONPATH` leaks Python 3.10 packages into the
  venv. `uv run pytest` is protected by `--disable-plugin-autoload`; `scripts/dev.sh`
  unsets `PYTHONPATH`.

Details and more in [docs/baseline.md](docs/baseline.md).

## License

MIT, see [LICENSE](LICENSE).
