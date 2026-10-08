#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "需要先安装 Python 3，然后重新运行。"
  read -r -p "按回车退出…"
  exit 1
fi
python3 server.py
read -r -p "服务已停止，按回车退出…"
