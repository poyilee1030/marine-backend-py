# Baseline

Append-only. Each step adds a section at the end; numbers already here never change.
Comparison method and tolerance: ROADMAP workflow rule 7.

---

## Step 1 — drone API, measured directly (2026-09-25)

Measured with `scripts/baseline_drone_direct.sh http://172.18.10.2:7070`, which bypasses
this backend. Every number comes from the drone's own `GET /get_drone_state`.

**Environment**

| Item | Value |
|---|---|
| Drone | drone-1 SITL, `172.18.10.2:7070`, container up 2 days |
| Coordinator | `/version` = 1.8.4, marlin-drone `7760d04` |
| Firmware | ArduPlane 4.6.3 (`/root/ardupilot` `3fc7011`), quadplane frame |
| Host tools | curl, jq 1.6, GNU coreutils `timeout`, util-linux `setsid` |
| Other GCS on drone-1 | none (no host connection to 172.18.10.2; :8000 is a ROS app, not marlin) |

**`/get_drone_state` fields (45)**

```
cur_task_id,session_id,lat,lng,alt_rel,alt_asl,yaw,pitch,roll,ground_track,
battery_voltage,battery_current,battery_temperature,air_speed,ground_speed,
vertical_speed,update_time,flight_mode,base_mode,system_status,is_armed,
is_ready_to_arm,hdop,vdop,gps_fix_type,satellites_visible,dist_to_wp,
mission_waypoint_index,mission_waypoint_count,mission_state,ch3_in,ch3_out,ch9_out,
dist_to_home,link_quality,time_in_air,dist_traveled,soc_percent,soh_percent,
est_capacity_ah,remaining_fw_min,remaining_vtol_min,eta_home_min,remaining_range_m,
timestamp
```

**Time units (G2), confirmed:** `update_time` is **seconds**, `timestamp` is
**milliseconds**. Sample: `update_time=1790334922`, `timestamp=1790334922905`,
host `time.time()=1790334922.908`. The container and the host share a clock.

**Takeoff / land, 3 runs** (takeoff to 10 m; `ALT_REACHED=9.5`, poll 0.5 s)

| Run | takeoff_s | land_s | takeoff POST latency | takeoff task | land task | start mode |
|---|---|---|---|---|---|---|
| 1 | 5.81 | 23.48 | 0.03 s | succeeded | succeeded | GUIDED (15), ready |
| 2 | 5.28 | 22.96 | 0.03 s | succeeded | succeeded | QLAND (20) → set GUIDED |
| 3 | 5.28 | 22.97 | 0.03 s | succeeded | succeeded | QLAND (20) → set GUIDED |
| **Median** | **5.28** | **22.97** | | | | |

- `takeoff_s`: takeoff POST sent → `alt_rel ≥ 9.5`. `land_s`: land POST sent → `is_armed == false`.
- The takeoff task already reads `succeeded` when `alt_rel` first reaches 9.5.
- Spread across the 3 runs: 0.53 s (takeoff) and 0.52 s (land). Polling at 0.5 s puts
  about ±0.5 s of quantisation on every number, so that spread is at the resolution limit.

**Regression windows** (rule 7: wider of ±30% and ±5 s around the median)

| Metric | Median | Window |
|---|---|---|
| takeoff_s | 5.28 | 0.28 – 10.28 s (±5 s is wider) |
| land_s | 22.97 | 16.08 – 29.86 s (±30% is wider) |

Rule 7 says to tighten this once step 1 has data. It is **not tightened yet**: 3 runs,
all from one SITL session, with a spread no bigger than the polling interval, do not
show what normal variation looks like. Revisit after step 3 adds 3 more runs.

**Pitfalls found in step 1**

1. **`is_ready_to_arm` depends on the flight mode.**
   *We expected:* `is_ready_to_arm=false` meant something was wrong (G7), and a takeoff
   in that state would be refused. *Actually:* it is ArduPlane's own pre-arm health bit,
   and `ModeQLand`, `ModeQRTL`, `ModeRTL` and `ModeInitializing` all return `false` from
   `_pre_arm_checks` (ArduPlane 4.6.3 `ArduPlane/mode.h`), shown as "mode not armable".
   A land leaves the aircraft in QLAND, so after every one of our own landings it reads
   `false`. `POST /api/takeoff` switches to GUIDED before arming, so it still flies
   (coordinator log 2026-09-24 06:06:13 disarm → 06:06:14 `ARM: ACCEPTED`). After
   `POST /api/set-mode {"mode":"GUIDED"}` it read `true` within 1 s.
   *Now:* the script switches to GUIDED and only then requires `is_ready_to_arm == true`.
2. **The takeoff POST answers in 0.03 s.**
   *We expected (ROADMAP step 3):* it waits for GUIDED + arm + NAV_TAKEOFF and can take a
   while, so the forwarding timeout would start at 30 s. *Actually:* 0.03 s in all 3 runs,
   starting from GUIDED or QLAND. Step 3 should size its timeout from this.
3. **ROS Humble's `PYTHONPATH` crashes pytest.**
   *We expected:* the uv venv is isolated. *Actually:* `~/.bashrc` sources
   `/opt/ros/humble/setup.bash`, and pytest auto-loads ROS's `launch_testing` plugin from
   the Python 3.10 path, which fails on `import yaml`. *Now:* `--disable-plugin-autoload`
   in `pyproject.toml`, and `unset PYTHONPATH` in `scripts/dev.sh`.
4. **`setsid cmd &` then `$!` is not the group leader.**
   *We expected:* `$!` names the new process group. *Actually:* in a non-interactive shell
   the backgrounded `setsid` is itself a group leader, so it forks and exits; `$!` is dead
   and `kill -- -$PGID` gets an empty PGID. *Now:* `scripts/smoke_health.sh` has the inner
   `bash` write its own pid (= the group id) to a file before `exec`.
5. **`pgrep -f <pattern>` matches the shell that typed it.**
   *We expected:* a leftover check on `uvicorn marine_backend` finds only uvicorn.
   *Actually:* it also matched the caller's own `bash -c "…"` command line, which
   contains the pattern. *Now:* match the process name (`pgrep -ax uvicorn`) and then
   filter arguments, or anchor the pattern (`^bash scripts/…`).
6. **Starlette 1.7 deprecates `httpx` in `TestClient`** (`StarletteDeprecationWarning`,
   "install `httpx2` instead"). `httpx2` 2.13.1 is pydantic's successor to httpx. Left as
   is for now (a warning, not a failure); the choice belongs in step 2 before it depends
   on `httpx.MockTransport`.

**Test self-check.** Each of the 8 script-contract tests failed first because the
script did not exist (exit 127), and was then shown to catch its own behaviour by
removing that behaviour from a copy of the script, one at a time
(`BASELINE_SCRIPT=<copy> uv run pytest tests/test_baseline_script.py`):

| Removed from the script | Tests that went red |
|---|---|
| switch to GUIDED when not ready | 6 of 8, including the bodies test |
| refuse an armed aircraft | `test_armed_aircraft_is_not_touched` |
| fail when still not ready after GUIDED | `test_not_ready_to_arm_fails_loudly_without_takeoff` |
| drone `detail` in the refusal message | `test_refused_takeoff_prints_the_drones_detail` |
| land an armed aircraft on abort | `test_takeoff_timeout_lands_the_aircraft_before_exiting` |
| an extra key in the takeoff body | `test_sends_exactly_the_bodies_the_drone_accepts` |
| swapped s/ms detection | `test_records_version_fields_and_time_units` |
| the `MEDIAN` line | `test_three_runs_report_timings_and_medians` |
| "unreachable" in the connection error | `test_unreachable_drone_fails_fast` |
