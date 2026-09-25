#!/usr/bin/env bash
# Start the backend with scripts/dev.sh, check GET /health, stop it, prove nothing is left.
#
#   scripts/smoke_health.sh            # exit 0 only if /health == {"ok":true} and no uvicorn remains
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=${PORT:-8100}
LOG=$(mktemp)
PGID=""

# Match on the process name (-x), then filter its arguments. `pgrep -f <pattern>` matches
# any command line containing the pattern -- including the shell that typed it.
leftovers() {
  { pgrep -ax uvicorn; pgrep -ax uv; } | grep -F "marine_backend.main:app --port $PORT" || true
}

cleanup() {
  local rc=$?
  trap - EXIT
  if [[ -n $PGID ]]; then
    kill -- "-$PGID" 2>/dev/null || true
    timeout 10 bash -c "while kill -0 -- -$PGID 2>/dev/null; do sleep 0.2; done" ||
      kill -KILL -- "-$PGID" 2>/dev/null || true
  fi
  if [[ -n $(leftovers) ]]; then
    echo "LEFTOVER uvicorn processes:" >&2
    leftovers >&2
    rc=1
  fi
  rm -f "$LOG"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if ss -ltn | grep -q ":$PORT "; then
  echo "port $PORT is already in use" >&2
  exit 1
fi

# The inner bash records its own pid before exec'ing, and that pid is the session and
# group leader. ($! is useless: setsid forks and exits when it is itself a group leader.)
setsid bash -c 'echo $$ >"$1"; exec scripts/dev.sh' _ "$LOG.pid" >"$LOG" 2>&1 </dev/null &
timeout 5 bash -c "until [[ -s '$LOG.pid' ]]; do sleep 0.05; done"
PGID=$(cat "$LOG.pid")
rm -f "$LOG.pid"

if ! timeout 30 bash -c "until curl -s localhost:$PORT/health >/dev/null; do sleep 0.3; done"; then
  echo "backend did not answer within 30s; log:" >&2
  cat "$LOG" >&2
  exit 1
fi
BODY=$(curl -s "localhost:$PORT/health")
echo "GET /health -> $BODY"
[[ $BODY == '{"ok":true}' ]]
