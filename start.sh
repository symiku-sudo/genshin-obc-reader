#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$(dirname "$0")"
python seed.py
exec python server.py --port "${1:-8766}"
