#!/bin/bash
# 一键刷新需求雷达（采集→打分→needs.json）。可加进 launchd/cron 每天自动跑。
# 用法：bash scripts/refresh.sh   或   ./scripts/refresh.sh
set -e
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
PY="$(command -v python3)"
echo "[$(date '+%F %T')] refresh start (python=$PY)" >> "logs/refresh-$(date +%Y%m%d).log"
"$PY" scripts/refresh.py >> "logs/refresh-$(date +%Y%m%d).log" 2>&1
echo "[$(date '+%F %T')] refresh done" >> "logs/refresh-$(date +%Y%m%d).log"
