#!/usr/bin/env bash
# 服务管理：bash restart.sh [fresh]
#   fresh = 清空测试数据库重新初始化
set -e
cd "$(dirname "$0")"

# 停掉已有 uvicorn（本脚本自身命令行不含 uvicorn 字样，不会误杀）
for pid in $(pgrep -f "python3 -m uvicorn" || true); do
  [ "$pid" != "$$" ] && kill "$pid" 2>/dev/null || true
done
sleep 1

if [ "$1" = "fresh" ]; then
  rm -f data/finance.db data/finance.db-wal data/finance.db-shm
  rm -rf data/books data/books.json
fi

nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
echo $! > .uvicorn.pid
for i in $(seq 1 30); do
  if curl -s -m 2 http://127.0.0.1:8000/api/health | grep -q ok; then
    echo "server up, pid $(cat .uvicorn.pid)"
    exit 0
  fi
  sleep 1
done
echo "server failed to start" >&2
tail -20 server.log >&2
exit 1
