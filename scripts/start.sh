#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "需要 uv 来创建 Python 环境：https://docs.astral.sh/uv/"
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "需要 Node.js 20+ 和 npm：https://nodejs.org/"
  exit 1
fi

export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.cache/uv}"
uv sync --frozen
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci --cache ../.cache/npm --no-audit --no-fund)
fi
(cd frontend && npm run build)

echo ""
echo "纸间已准备好：http://127.0.0.1:8765"
echo "首次使用：导入 MinerU 论文 → 设置翻译服务 → 开始翻译。"
echo "按 Ctrl+C 停止应用。"
echo ""
exec .venv/bin/python scripts/serve.py
