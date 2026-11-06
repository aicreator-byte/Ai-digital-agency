#!/bin/bash
# Cek status bridge WA. Keluar 0 bila tersambung (ready:true).
set -u
URL="${WA_BRIDGE_URL:-http://127.0.0.1:3000}"
HDR=()
[ -n "${WA_BRIDGE_TOKEN:-}" ] && HDR=(-H "x-token: $WA_BRIDGE_TOKEN")
out=$(curl -s -m 10 "${HDR[@]}" "$URL/status" 2>/dev/null) || { echo "bridge tidak jalan di $URL"; exit 1; }
echo "$out"
echo "$out" | grep -q '"ready":true'
