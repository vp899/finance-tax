#!/usr/bin/env bash
# 一键启动前后端：bash start.sh
set -e
cd "$(dirname "$0")"

echo "==> 启动后端 (FastAPI :8000)"
bash backend/restart.sh

echo "==> 启动前端 (Next.js :3000)"
cd frontend
[ -d node_modules ] || npm install
[ -f .next/BUILD_ID ] || npm run build
nohup npm run start > server.log 2>&1 &
echo $! > .next.pid
sleep 3
echo "前端：http://localhost:3000  后端 API 文档：http://localhost:8000/docs"
