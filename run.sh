#!/bin/bash

pkill -f "python aha.py"
while pgrep -f "python aha.py" > /dev/null; do
    echo "🕒 等待进程退出..."
    sleep 1
done

cd "$(dirname "$0")"

tmux new -d -s aha 'env BOT_ENV="main" python aha.py'

echo "✅ 已启动 Aha。附加会话: tmux a -t aha | 分离: Ctrl+B D | 终止: tmux kill-session -t aha"
