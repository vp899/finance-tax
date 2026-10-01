#!/usr/bin/env bash
# 启动后端：bash run.sh
cd "$(dirname "$0")"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
