#!/bin/bash
# 启动取件码服务
# 首次运行若提示无法读取短信，请在 系统设置 > 隐私与安全性 > 信息与照片 中授权当前终端
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r server/requirements.txt
PORT="${QJK_PORT:-8787}"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用，服务可能已在运行。"
  echo "如需换端口启动：QJK_PORT=8788 $0"
  exit 1
fi
exec .venv/bin/python -m uvicorn server.main:app --host "${QJK_HOST:-0.0.0.0}" --port "$PORT"
