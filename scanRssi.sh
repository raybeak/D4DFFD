#!/usr/bin/env bash
# Repeatedly scan 2.4GHz only, read RSSI of target SSID, publish as JSON lines.
#
# Usage:
#   sudo ./scan_rssi.sh [options]
#
# Options:
#   --ssid NAME          target SSID (default: DRONE-01)
#   --iface IF           Wi-Fi interface (default: first found by `iw dev`)
#   --udp HOST:PORT      send JSON to Pi over network (Tailscale IP / MagicDNS name / LAN IP)
#   --serial DEV         send JSON over serial (GPIO UART or USB serial), e.g. /dev/ttyACM0
#   --baud N             serial baud rate (default: 115200)
#
# Examples:
#   sudo ./scan_rssi.sh --udp raspberrypi:5005          # Tailscale MagicDNS
#   sudo ./scan_rssi.sh --udp 100.101.102.103:5005      # Tailscale IP
#   sudo ./scan_rssi.sh --serial /dev/ttyS0             # GPIO UART
#
# Without --udp/--serial it only prints and logs locally.

SSID="DRONE-01"
IFACE=""
UDP=""
SERIAL=""
BAUD=115200

while [ $# -gt 0 ]; do
  case "$1" in
    --ssid)   SSID="$2"; shift 2 ;;
    --iface)  IFACE="$2"; shift 2 ;;
    --udp)    UDP="$2"; shift 2 ;;
    --serial) SERIAL="$2"; shift 2 ;;
    --baud)   BAUD="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo: sudo $0 $*"
  exit 1
fi

[ -z "$IFACE" ] && IFACE=$(iw dev | awk '$1=="Interface"{print $2; exit}')
if [ -z "$IFACE" ]; then
  echo "No Wi-Fi interface found (check: iw dev)"
  exit 1
fi

NODE=$(hostname)

# 2.4GHz channels 1-13 (KR)
FREQS="2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462 2467 2472"

LOG="$HOME/es/rssi_${NODE}.jsonl"
mkdir -p "$(dirname "$LOG")"

# Serial setup
if [ -n "$SERIAL" ]; then
  if [ ! -e "$SERIAL" ]; then
    echo "Serial device not found: $SERIAL"
    exit 1
  fi
  stty -F "$SERIAL" "$BAUD" raw -echo
fi

# UDP target split
if [ -n "$UDP" ]; then
  UDP_HOST="${UDP%:*}"
  UDP_PORT="${UDP##*:}"
fi

send() {
  local line="$1"
  echo "$line" >> "$LOG"
  if [ -n "$UDP" ]; then
    # bash built-in UDP, no extra package needed
    echo "$line" > "/dev/udp/$UDP_HOST/$UDP_PORT" 2>/dev/null || echo "  (udp send failed)"
  fi
  if [ -n "$SERIAL" ]; then
    echo "$line" > "$SERIAL" 2>/dev/null || echo "  (serial send failed)"
  fi
}

echo "node=$NODE iface=$IFACE ssid=$SSID udp=${UDP:-off} serial=${SERIAL:-off} log=$LOG  (Ctrl+C to stop)"

while true; do
  t0=$(date +%s%N)
  out=$(iw dev "$IFACE" scan flush freq $FREQS 2>&1)
  t1=$(date +%s%N)
  ms=$(( (t1 - t0) / 1000000 ))

  # Busy: retry shortly
  if echo "$out" | grep -q "busy"; then
    sleep 0.5
    continue
  fi

  # Take signal of the BSS block whose SSID exactly matches
  rssi=$(echo "$out" | awk -v s="$SSID" '
    /^BSS /      { sig="" }
    /signal:/    { sig=$2 }
    $1=="SSID:"  { name=$0; sub(/^[ \t]*SSID: /, "", name); if (name==s && sig!="") { print sig; exit } }
  ')

  ts=$(date +%Y-%m-%dT%H:%M:%S.%3N%:z)
  if [ -n "$rssi" ]; then
    json="{\"ts\":\"$ts\",\"node\":\"$NODE\",\"iface\":\"$IFACE\",\"ssid\":\"$SSID\",\"found\":true,\"rssi_dbm\":$rssi,\"scan_ms\":$ms}"
  else
    json="{\"ts\":\"$ts\",\"node\":\"$NODE\",\"iface\":\"$IFACE\",\"ssid\":\"$SSID\",\"found\":false,\"rssi_dbm\":null,\"scan_ms\":$ms}"
  fi

  echo "$json"
  send "$json"
done
