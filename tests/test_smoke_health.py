"""scripts/smoke_health.sh's leftover check, against a real uvicorn (never SITL).

The case from the code review of PR #1: `uvicorn --reload` serves from a
multiprocessing child (`python -c "from multiprocessing.spawn import spawn_main…"`),
and that child is what holds the port. Kill only the processes whose command line names
the app, and the child lives on as an orphan. leftovers() must still report it.
"""

import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SMOKE = REPO / "scripts" / "smoke_health.sh"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def leftovers(pgid: int, port: int) -> str:
    # Run the script's own function, not a copy of it.
    fn = re.search(r"^leftovers\(\) \{.*?^\}", SMOKE.read_text(), re.S | re.M).group(0)
    return subprocess.run(["bash", "-c", f"{fn}\nleftovers"], capture_output=True, text=True,
                          env={**os.environ, "PGID": str(pgid), "PORT": str(port)}).stdout


def test_leftovers_sees_the_reload_child_that_holds_the_port():
    port = free_port()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    server = subprocess.Popen(["bash", str(REPO / "scripts" / "dev.sh")], cwd=REPO,
                              env={**env, "PORT": str(port)}, start_new_session=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pgid = server.pid
    try:
        deadline = time.time() + 30
        while subprocess.run(["curl", "-s", f"localhost:{port}/health"],
                             capture_output=True).returncode != 0:
            assert time.time() < deadline, "backend did not start"
            time.sleep(0.3)
        named = subprocess.run(["pgrep", "-f", f"marine_backend.main:app --port {port}"],
                               capture_output=True, text=True).stdout.split()
        for pid in named:
            os.kill(int(pid), signal.SIGKILL)
        time.sleep(1)

        found = leftovers(pgid, port)
    finally:
        os.killpg(pgid, signal.SIGKILL)

    assert f":{port}" in found or "spawn_main" in found, found
