#!/usr/bin/env bash
# Disposable public Linux runner only. No user state or arbitrary target.
set -euo pipefail
name="winebot-cpa0-$$"
image='debian@sha256:cedb1ef40439206b673ee8b33a46a03a0c9fa90bf3732f54704f99cb061d2c5a'
container=''
cleanup() {
  if [ -n "$container" ]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
fail() { printf 'CPA0 stage=%s result=FAIL\n' "$1" >&2; exit 1; }
pass() { printf 'CPA0 stage=%s result=PASS\n' "$1"; }
[ "$(docker info --format '{{.CgroupVersion}}')" = 2 ] || fail cgroup_version
container="$(docker run -d --name "$name" --network none --read-only --user 1000:1000 \
  --cap-drop ALL --security-opt no-new-privileges --cpus .5 --memory 128m \
  --memory-swap 128m --pids-limit 24 --tmpfs /tmp:rw,nosuid,nodev,mode=1777,size=32m \
  --init "$image" sleep 60)" || fail container_start
[[ "$container" =~ ^[0-9a-f]{64}$ ]] || fail container_identity
pid="$(docker inspect --format '{{.State.Pid}}' "$container")"
[[ "$pid" =~ ^[1-9][0-9]*$ ]] || fail pid_identity
relative="$(sudo cat "/proc/$pid/cgroup" | sed -n 's/^0:://p')"
[[ "$relative" = /* && "$relative" != / && "$relative" == *"$container"* ]] || fail scope_identity
scope="/sys/fs/cgroup$relative"
read_counter() { sudo awk -v key="$2" '$1 == key {print $2}' "$scope/$1"; }
[ "$(sudo cat "$scope/cpu.max")" = '50000 100000' ] || fail cpu_limit
[ "$(sudo cat "$scope/memory.max")" = 134217728 ] || fail memory_limit
[ "$(sudo cat "$scope/memory.swap.max")" = 0 ] || fail swap_limit
[ "$(sudo cat "$scope/pids.max")" = 24 ] || fail pids_limit
pass kernel_leaf_limits
docker exec "$container" sh -eu -c '
  test "$(id -u)" = 1000
  test "$(id -g)" = 1000
  grep -Eq "^CapEff:[[:space:]]+0000000000000000$" /proc/self/status
  grep -Eq "^NoNewPrivs:[[:space:]]+1$" /proc/self/status
  test ! -e /var/run/docker.sock
  test ! -e /winebot-control
  if (echo unexpected > /cpa0-denied) 2>/dev/null; then exit 1; fi
  test ! -w /sys/fs/cgroup/pids.max
  echo writable > /tmp/cpa0
' >/dev/null 2>&1 || fail permissions
pass permissions
before="$(read_counter cpu.stat nr_throttled)"
set +e
docker exec "$container" timeout 3s sh -c 'while :; do :; done' >/dev/null 2>&1
rc=$?
set -e
[ "$rc" = 124 ] || fail cpu_fixture
after="$(read_counter cpu.stat nr_throttled)"
[[ "$before" =~ ^[0-9]+$ && "$after" =~ ^[0-9]+$ ]] && (( after > before )) || fail cpu_throttle
pass cpu_throttle
# Demonstrate accounted memory allocation, not OOM or ancestor reservation.
before="$(sudo cat "$scope/memory.current")"
docker exec "$container" dd if=/dev/zero of=/tmp/cpa0-memory bs=1M count=16 >/dev/null 2>&1 || fail memory_fixture
after="$(sudo cat "$scope/memory.current")"
(( after > before + 8*1024*1024 && after <= 134217728 )) || fail memory_accounting
pass memory_accounting
# At most 40 short-lived children, kernel hard cap is 24; never touch host PIDs.
before="$(read_counter pids.events max)"
docker exec "$container" sh -c 'i=0; while [ "$i" -lt 40 ]; do sleep 15 & i=$((i+1)); done; wait' >/dev/null 2>&1 &
probe=$!
observed=0
for _ in $(seq 1 40); do
  after="$(read_counter pids.events max)"
  if [[ "$after" =~ ^[0-9]+$ ]] && (( after > before )); then observed=1; break; fi
  sleep .1
done
[ "$observed" = 1 ] || fail pid_denial
[ "$(sudo cat "$scope/pids.current")" -le 24 ] || fail pid_ceiling
pass pid_denial
# Host control path must remain usable while guest is PID-constrained.
# This is a Docker stop witness, not durable STOP/keeper qualification.
timeout 10s docker stop -t 1 "$container" >/dev/null || fail host_stop
[ "$(docker inspect --format '{{.State.Running}}' "$container")" = false ] || fail host_stop
wait "$probe" || true
pass host_stop
