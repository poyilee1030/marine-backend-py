"""Contract of scripts/baseline_drone_direct.sh, run against tests/fake_drone.py (never SITL).

The contract comes from ROADMAP step 1 and marlin-drone's drone_api_server.py, not from
the script: a not-ready aircraft fails loudly before any takeoff is sent, a refused
takeoff prints the drone's own detail, an aircraft left armed by an abort is landed,
and a finished run prints one RUN line per flight plus the medians.
"""

import os
import re
import subprocess
import time
from pathlib import Path

from tests.fake_drone import GUIDED, QRTL, FakeDrone

# BASELINE_SCRIPT points the suite at a mutated copy, to prove each test can fail.
SCRIPT = Path(
    os.environ.get("BASELINE_SCRIPT")
    or Path(__file__).resolve().parent.parent / "scripts" / "baseline_drone_direct.sh"
)
FAST = {"POLL_S": "0.05", "READY_TIMEOUT_S": "1", "TAKEOFF_TIMEOUT_S": "5", "LAND_TIMEOUT_S": "5",
        "ABORT_WATCH_S": "0.3"}


def run(url: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), url],
        env={**os.environ, **FAST, **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_three_runs_report_timings_and_medians():
    drone = FakeDrone(flight_mode=QRTL)
    with drone as url:
        result = run(url)

    assert result.returncode == 0, result.stdout + result.stderr
    runs = re.findall(
        r"^RUN (\d) takeoff_s=([\d.]+) land_s=([\d.]+) takeoff_post_s=[\d.]+ "
        r"takeoff_task=(\S+) land_task=(\S+)$",
        result.stdout,
        re.M,
    )
    assert [r[0] for r in runs] == ["1", "2", "3"]
    assert all(r[4] == "succeeded" for r in runs)
    assert re.search(r"^MEDIAN takeoff_s=[\d.]+ land_s=[\d.]+$", result.stdout, re.M)


def test_records_version_fields_and_time_units():
    with FakeDrone() as url:
        result = run(url, RUNS="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r"^VERSION 1\.8\.4$", result.stdout, re.M)
    fields = re.search(r"^FIELDS (.+)$", result.stdout, re.M)
    assert fields and {"update_time", "timestamp", "alt_rel", "is_ready_to_arm"} <= set(
        fields.group(1).split(",")
    )
    assert re.search(r"^UNITS update_time=s timestamp=ms$", result.stdout, re.M)


def test_sends_exactly_the_bodies_the_drone_accepts():
    # extra="forbid" on the drone side: any extra key is a 422.
    drone = FakeDrone()
    with drone as url:
        result = run(url, RUNS="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert drone.posts() == [
        ("/api/set-mode", {"mode": "GUIDED"}),
        ("/api/takeoff", {"altitude": 10}),
        ("/api/land", {}),
    ]


def test_not_ready_to_arm_fails_loudly_without_takeoff():
    drone = FakeDrone(flight_mode=QRTL, ready_after_guided=False)
    with drone as url:
        result = run(url)

    assert result.returncode == 1
    assert re.search(r"PRECONDITION FAILED: is_ready_to_arm=false flight_mode=15 gps_fix_type=6",
                     result.stderr)
    assert "/api/takeoff" not in [p for p, _ in drone.posts()]


def test_armed_aircraft_is_not_touched():
    # Something else is flying it: no mode switch, no takeoff, no land.
    drone = FakeDrone(flight_mode=GUIDED, is_armed=True)
    with drone as url:
        result = run(url)

    assert result.returncode == 1
    assert "PRECONDITION FAILED: is_armed=true" in result.stderr
    assert drone.posts() == []


def test_refused_takeoff_prints_the_drones_detail():
    drone = FakeDrone(takeoff_status=409, takeoff_detail="PreArm: Battery 1 low voltage")
    with drone as url:
        result = run(url)

    assert result.returncode == 1
    assert "HTTP 409" in result.stderr
    assert "PreArm: Battery 1 low voltage" in result.stderr


def test_takeoff_timeout_lands_the_aircraft_before_exiting():
    drone = FakeDrone(climb_rate=0.0)
    with drone as url:
        result = run(url, TAKEOFF_TIMEOUT_S="1")

    assert result.returncode == 1
    assert "TIMEOUT" in result.stderr
    assert [p for p, _ in drone.posts()][-1] == "/api/land"


def test_abort_while_takeoff_is_still_arming_still_lands():
    # The takeoff request outlives the script's own timeout: the aircraft is not armed
    # when the script gives up, and arms a second later. "Not armed right now" must not
    # be taken to mean "nothing to land" (code review of PR #1).
    drone = FakeDrone(takeoff_delay=2.0)
    with drone as url:
        result = run(url, COMMAND_TIMEOUT_S="1", ABORT_WATCH_S="4")
        # Look only after the late takeoff has certainly armed the aircraft.
        time.sleep(drone.takeoff_delay + drone.land_s + 0.5)
        final = drone.state()

    assert result.returncode == 1
    assert final["is_armed"] is False, result.stderr


def test_lower_altitude_uses_a_matching_threshold():
    # ALTITUDE=5 must not wait for the 10 m run's 9.5 m threshold (code review of PR #1).
    with FakeDrone() as url:
        result = run(url, RUNS="1", ALTITUDE="5")

    assert result.returncode == 0, result.stderr


def test_unreachable_drone_fails_fast():
    result = run("http://127.0.0.1:9")

    assert result.returncode == 1
    assert "unreachable" in result.stderr
