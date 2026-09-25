# CLAUDE.md

Single entry point for an agent or a new session. The plan, the decisions and the
workflow rules live in `ROADMAP.md`; read its **工作流程規則** before starting a step.

## What this is

A minimal FastAPI backend (:8100) between the browser (`marine-frontend`) and each
drone container's coordinator HTTP API (:7070). For drone developers to test by hand.
Not a production GCS.

## Setup and run

```bash
uv sync                 # Python 3.12 is pinned (.python-version); uv installs it
uv run pytest           # unit tests; never touch SITL (workflow rule 8)
scripts/dev.sh          # uvicorn on :8100 with --reload
scripts/smoke_health.sh # start, GET /health, stop, prove no uvicorn is left
```

**ROS Humble on this host.** `~/.bashrc` sources `/opt/ros/humble/setup.bash`, which
puts Python 3.10 site-packages on `PYTHONPATH`. That path is searched before the venv,
and pytest auto-loads ROS's `launch_testing` plugin from it and crashes. Hence
`addopts = "--disable-plugin-autoload"` in `pyproject.toml` and `unset PYTHONPATH` in
`scripts/dev.sh`. Keep both; any new script that runs Python must unset it too.

## SITL (prerequisite for scripts/, never for pytest)

```bash
cd ~/poyi/marlin-drone
bash multiple_sitl/create_dockers.sh 1 --autopilot ardupilot   # drone-1 -> 172.18.10.2:7070
curl -s http://172.18.10.2:7070/version                         # {"version":"1.8.4"}
```

- `scripts/baseline_drone_direct.sh <drone_url>` flies the drone for real: 3 takeoffs
  to 10 m and 3 landings. Before running it, make sure no other GCS (marlin dashboard,
  gcs-server-v1) is commanding the same drone (workflow rule 9).
- `is_ready_to_arm` is ArduPlane's own pre-arm verdict and is **always false in QLAND,
  QRTL and RTL** ("mode not armable"). A land leaves the aircraft in QLAND. The script
  switches to GUIDED first, then requires `is_ready_to_arm == true`.
- Drone API source of truth: `~/poyi/marlin-drone/drone/drone_api_server.py`.

## Workflow

- One step = one branch `step-N-<short>` = one PR titled `step-N: <goal>`.
- Tests first (workflow rule 10): watch every test fail for the right reason before
  writing the code. Script contracts are tested against `tests/fake_drone.py`.
- Measure on the drone, not on this backend's responses (workflow rule 4).
- Append-only `docs/baseline.md`: each step adds a section; old numbers never change.
- PRs: `gh` is not installed; open them through the GitHub REST API with the token
  already in the `origin` remote URL. Never print or commit that token.
- Code review happens after the PR is open, in a clean session (`/code-review`).
