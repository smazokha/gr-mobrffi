#!/usr/bin/env bash
set -euo pipefail

HOST="192.168.10.10"
USER="smazokha"
SESSION="emit"
REMOTE_EMIT="~/probe_request_injection/emit/emit.sh"

CHANNEL="36"
MAC="11:22:33:44:55:66"
INTERVAL="0.01"
SSID="mobintel"

# Quieter SSH: no TTY, minimal logs, fail fast if keys aren’t set
SSH_OPTS=(-T -o LogLevel=ERROR -o BatchMode=yes)

usage() {
  cat <<EOF
Usage: $(basename "$0") --device NAME [options]
  --device NAME          (required) e.g., alfa_01
  --host HOST            Default: ${HOST}
  --user USER            Default: ${USER}
  --session NAME         Default: ${SESSION}
  --channel N            Default: ${CHANNEL}
  --mac MAC              Default: ${MAC}
  --interval SEC         Default: ${INTERVAL}
  --ssid NAME            Default: ${SSID}
EOF
}

DEVICE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --device)   DEVICE="${2:-}"; shift 2 ;;
    --host)     HOST="${2:-}"; shift 2 ;;
    --user)     USER="${2:-}"; shift 2 ;;
    --session)  SESSION="${2:-}"; shift 2 ;;
    --channel)  CHANNEL="${2:-}"; shift 2 ;;
    --mac)      MAC="${2:-}"; shift 2 ;;
    --interval) INTERVAL="${2:-}"; shift 2 ;;
    --ssid)     SSID="${2:-}"; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done
[[ -n "${DEVICE}" ]] || { echo "Error: --device is required." >&2; usage; exit 1; }

REMOTE="${USER}@${HOST}"

start_remote() {
  # run remote emit (which starts tmux and returns)
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "${REMOTE_EMIT} -c ${CHANNEL} --mac ${MAC} --interval ${INTERVAL} --ssid ${SSID} -i ${DEVICE}"
}

kill_remote() {
  # be quiet if session missing
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "tmux has-session -t ${SESSION} 2>/dev/null && tmux kill-session -t ${SESSION} || true" \
    >/dev/null 2>&1 || true
}

CLEANED=0
cleanup() {
  (( CLEANED )) && return
  CLEANED=1
  kill_remote
}
trap cleanup EXIT INT TERM

start_remote

echo "Press ENTER to stop '${SESSION}' (or Ctrl-C)."
read -r _

cleanup
trap - EXIT
echo "TX stopped."
