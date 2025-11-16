#!/bin/bash

script_dir="$(cd "$(dirname "$0")" && pwd)"

KILL_ONLY=0
if [ $# -gt 1 ]; then
    echo "Usage: $0 [-k|--kill-only]"
    exit 64
elif [ $# -eq 1 ]; then
    case "$1" in
        -k|--kill-only)
            KILL_ONLY=1
            ;;
        *)
            exit 64
            ;;
    esac
fi

ps -eo pid,cmd | grep "[a]ha.py" | grep -vE "tmux |screen |multiprocessing" | awk '{print $1}' | xargs -r kill

while ps -eo pid,cmd | grep "[a]ha.py" | grep -vE "tmux |screen |multiprocessing" > /dev/null; do
    echo "🕒 等待进程退出..."
    sleep 1
done

if [ "$KILL_ONLY" -eq 1 ]; then
    exit 0
fi

cmd="env BOT_ENV=main python3 $script_dir/aha.py"
[ -d "$script_dir/.venv" ] && cmd="source $script_dir/.venv/bin/activate && $cmd"

if command -v tmux >/dev/null 2>&1; then
    tmux new -d -s aha bash -c "$cmd"
    echo "✅ 已启动 Aha。附加会话: tmux a -t aha | 分离: Ctrl+B D | 终止: $script_dir/$(basename "$0") -k"
else
    screen -dmS aha bash -c "$cmd"
    echo "✅ 已启动 Aha。附加会话: screen -r aha | 分离: Ctrl+A D | 终止: $script_dir/$(basename "$0") -k"
fi