#!/usr/bin/env bash
# Characterise one drone's coordinator API directly, bypassing marine-backend-py.
#
#   scripts/baseline_drone_direct.sh http://172.18.10.2:7070
#
# Prints, on stdout, lines meant to be pasted into docs/baseline.md:
#   VERSION <coordinator version>
#   FIELDS  <comma-separated /get_drone_state keys>
#   UNITS   update_time=<s|ms> timestamp=<s|ms>
#   RUN <i> takeoff_s=… land_s=… takeoff_post_s=… takeoff_task=<state> land_task=<state>
#   MEDIAN  takeoff_s=… land_s=…
# Progress goes to stderr. Exit 0 only if every run took off and landed.
#
# takeoff_s: takeoff POST sent -> the drone's own alt_rel >= ALT_REACHED.
# land_s:    land POST sent    -> the drone's own is_armed == false.
# Both are measured on the drone (ROADMAP workflow rule 4), never on a response.
#
# Precondition (ROADMAP step 1): is_ready_to_arm == true, else fail loudly. In ArduPlane
# 4.6.3 QLAND, QRTL and RTL fail pre-arm by design ("mode not armable",
# ArduPlane/mode.h), and a land leaves the aircraft in QLAND, so every run first
# switches to GUIDED (whose pre-arm check passes) when the aircraft is not ready.
# An armed aircraft is never touched: something else is flying it.
set -euo pipefail

DRONE=${1:?usage: $0 <drone_url>}
DRONE=${DRONE%/}
RUNS=${RUNS:-3}
ALTITUDE=${ALTITUDE:-10}
# "Reached" = within 0.5 m of the target: 9.5 for the default 10 m (ROADMAP step 1), the
# same tolerance as marlin-drone's drone/scratch/take_off_land.py. Follows ALTITUDE.
ALT_REACHED=${ALT_REACHED:-$(awk "BEGIN { print $ALTITUDE - 0.5 }")}
POLL_S=${POLL_S:-0.5}
READY_TIMEOUT_S=${READY_TIMEOUT_S:-10}
TAKEOFF_TIMEOUT_S=${TAKEOFF_TIMEOUT_S:-120}  # the drone's own DroneParams.TAKEOFF_TIMEOUT
LAND_TIMEOUT_S=${LAND_TIMEOUT_S:-180}
# takeoff answers only after GUIDED + arm + NAV_TAKEOFF are all acknowledged.
COMMAND_TIMEOUT_S=${COMMAND_TIMEOUT_S:-60}
# After an abort, how long to keep watching for a takeoff that is still arming.
ABORT_WATCH_S=${ABORT_WATCH_S:-15}

TMP=$(mktemp -d)
COMMANDED=0  # 1 from sending a takeoff until we have seen that flight disarm

log() { echo "[$(date +%H:%M:%S)] $*" >&2; }
die() { echo "$*" >&2; exit 1; }
now() { date +%s.%N; }
calc() { awk "BEGIN { print $* }"; }
is_true() { [[ $(awk "BEGIN { print ($*) ? 1 : 0 }") == 1 ]]; }

# req METHOD PATH [BODY] [TIMEOUT]  ->  sets CODE and BODY. Never call it in $(…):
# its die must exit the script, not a subshell.
req() {
  local method=$1 path=$2 body=${3:-} timeout=${4:-5} rc=0
  local args=(-sS -m "$timeout" -o "$TMP/body" -w '%{http_code}' -X "$method")
  [[ -n $body ]] && args+=(-H 'content-type: application/json' -d "$body")
  CODE=$(curl "${args[@]}" "$DRONE$path" 2>"$TMP/err") || rc=$?
  ((rc == 0)) || die "drone unreachable: $method $path: $(cat "$TMP/err")"
  BODY=$(cat "$TMP/body")
}

read_state() {
  req GET /get_drone_state
  [[ $CODE == 200 ]] || die "GET /get_drone_state -> HTTP $CODE $BODY"
  STATE=$BODY
}
field() { jq -r ".$1" <<<"$STATE"; }

task_state() {
  req GET "/tasks/$1"
  if [[ $CODE == 200 ]]; then jq -r .state <<<"$BODY" >"$TMP/task"; else echo "http_$CODE" >"$TMP/task"; fi
}

abort_land() {
  log "$1: sending POST /api/land"
  curl -sS -m 30 -X POST -H 'content-type: application/json' -d '{}' "$DRONE/api/land" >&2 || true
  echo >&2
}

cleanup() {
  local rc=$? t0 s
  trap - EXIT
  if ((COMMANDED)); then
    # An abort between takeoff and touchdown must not leave the aircraft flying. "Not
    # armed right now" proves nothing: a takeoff POST that timed out or was interrupted
    # may still be arming on the drone. So watch for ABORT_WATCH_S and land whenever the
    # aircraft is armed outside QLAND (20) -- already landing needs no second command.
    t0=$(now)
    while is_true "$(now) - $t0 < $ABORT_WATCH_S"; do
      if s=$(curl -sS -m 5 "$DRONE/get_drone_state" 2>/dev/null) &&
        jq -e '.is_armed == true and .flight_mode != 20' >/dev/null 2>&1 <<<"$s"; then
        abort_land "aborting with the aircraft armed outside QLAND"
      fi
      sleep "$POLL_S"
    done
  fi
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

unit_of() {  # value now -> s | ms | unknown
  awk -v v="$1" -v n="$2" 'function abs(x) { return x < 0 ? -x : x }
    BEGIN { if (abs(v - n) < 86400) print "s"; else if (abs(v / 1000 - n) < 86400) print "ms"; else print "unknown" }'
}

median() {  # values… -> median
  printf '%s\n' "$@" | sort -g | awk '{ a[NR] = $1 } END { print (NR % 2) ? a[(NR + 1) / 2] : (a[NR / 2] + a[NR / 2 + 1]) / 2 }'
}

preflight() {
  read_state
  if [[ $(field is_armed) == true ]]; then
    die "PRECONDITION FAILED: is_armed=true flight_mode=$(field flight_mode) — something else is flying it; not touching it"
  fi
  if [[ $(field is_ready_to_arm) != true ]]; then
    log "is_ready_to_arm=false in flight_mode=$(field flight_mode); switching to GUIDED"
    req POST /api/set-mode '{"mode":"GUIDED"}' 15
    [[ $CODE == 200 ]] || die "POST /api/set-mode GUIDED -> HTTP $CODE $BODY"
    local t0
    t0=$(now)
    while read_state && [[ $(field is_ready_to_arm) != true ]]; do
      is_true "$(now) - $t0 < $READY_TIMEOUT_S" || break
      sleep "$POLL_S"
    done
  fi
  if [[ $(field is_ready_to_arm) != true ]]; then
    die "PRECONDITION FAILED: is_ready_to_arm=false flight_mode=$(field flight_mode) gps_fix_type=$(field gps_fix_type)"
  fi
}

fly_once() {  # run index -> prints one RUN line
  local i=$1 t0 t_post t1 takeoff_id land_id takeoff_s land_s alt
  preflight

  log "run $i: POST /api/takeoff altitude=$ALTITUDE"
  COMMANDED=1
  t0=$(now)
  req POST /api/takeoff "{\"altitude\":$ALTITUDE}" "$COMMAND_TIMEOUT_S"
  t_post=$(now)
  [[ $CODE == 200 ]] || die "takeoff refused: HTTP $CODE $BODY"
  takeoff_id=$(jq -r .task_id <<<"$BODY")

  while true; do
    read_state
    alt=$(field alt_rel)
    is_true "$alt >= $ALT_REACHED" && break
    is_true "$(now) - $t0 < $TAKEOFF_TIMEOUT_S" ||
      die "TIMEOUT: alt_rel=$alt did not reach $ALT_REACHED within ${TAKEOFF_TIMEOUT_S}s"
    sleep "$POLL_S"
  done
  takeoff_s=$(calc "$(now) - $t0")
  task_state "$takeoff_id"
  local takeoff_task
  takeoff_task=$(cat "$TMP/task")
  log "run $i: alt_rel=$alt after ${takeoff_s}s (task $takeoff_id: $takeoff_task)"

  log "run $i: POST /api/land"
  t1=$(now)
  req POST /api/land '{}' "$COMMAND_TIMEOUT_S"
  [[ $CODE == 200 ]] || die "land refused: HTTP $CODE $BODY"
  land_id=$(jq -r .task_id <<<"$BODY")

  while true; do
    read_state
    [[ $(field is_armed) == false ]] && break
    is_true "$(now) - $t1 < $LAND_TIMEOUT_S" ||
      die "TIMEOUT: still armed at alt_rel=$(field alt_rel) after ${LAND_TIMEOUT_S}s"
    sleep "$POLL_S"
  done
  land_s=$(calc "$(now) - $t1")
  COMMANDED=0
  task_state "$land_id"
  log "run $i: disarmed after ${land_s}s (task $land_id: $(cat "$TMP/task"))"

  printf 'RUN %d takeoff_s=%.2f land_s=%.2f takeoff_post_s=%.2f takeoff_task=%s land_task=%s\n' \
    "$i" "$takeoff_s" "$land_s" "$(calc "$t_post - $t0")" "$takeoff_task" "$(cat "$TMP/task")"
  TAKEOFFS+=("$takeoff_s")
  LANDS+=("$land_s")
}

req GET /version
[[ $CODE == 200 ]] || die "GET /version -> HTTP $CODE $BODY"
echo "VERSION $(jq -r .version <<<"$BODY")"

read_state
t_now=$(now)
echo "FIELDS $(jq -r 'keys_unsorted | join(",")' <<<"$STATE")"
echo "UNITS update_time=$(unit_of "$(field update_time)" "$t_now") timestamp=$(unit_of "$(field timestamp)" "$t_now")"
log "sample: update_time=$(field update_time) timestamp=$(field timestamp) host_now=$t_now"

TAKEOFFS=()
LANDS=()
for ((i = 1; i <= RUNS; i++)); do
  fly_once "$i"
done

printf 'MEDIAN takeoff_s=%.2f land_s=%.2f\n' "$(median "${TAKEOFFS[@]}")" "$(median "${LANDS[@]}")"
