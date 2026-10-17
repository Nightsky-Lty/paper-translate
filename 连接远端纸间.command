#!/bin/zsh
cd "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
python3 scripts/connect_remote.py --host tencentcloud
if [[ $? -ne 0 ]]; then
  read -k 1 "?按任意键关闭…"
fi
